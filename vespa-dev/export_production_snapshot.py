"""
Prefect flow: snapshot the production Vespa corpus to S3, once a day.

`feed_from_production.py` currently runs `vespa visit` against production on
every ad hoc dev-instance feed (see its module docstring), which is slow and
puts read load on production every time someone iterates. This flow is the
"export" half that docstring already earmarks: it does the same `vespa
visit`, but on a schedule, and writes the result to S3 as sharded JSONL
instead of a single ~10GB file - matching the folder-of-parts pattern
`vespa-feeder/flow.py`'s `download_from_s3` already expects (a non-`.jsonl`
S3 key is treated as a prefix and every object under it is downloaded and
fed). `feed_from_production.py` is not yet wired up to read from this
snapshot instead of production directly - that's a follow-up.

Why shard into many ~200MB files rather than one big one:
- Fault isolation / cheap retry: if shard 47 of 200 fails to upload (or,
  downstream, fails to feed), only that shard needs retrying - not the whole
  corpus. A single giant object means any failure restarts the entire
  transfer from scratch.
- Parallelism: S3 throughput and the Vespa feed client both scale by having
  multiple concurrent transfers, not one wide one. Many objects let
  producers/consumers work on several at once instead of serializing on a
  single stream.
- Bounded memory/disk: a consumer processes one ~200MB file at a time rather
  than needing to hold (or stream-parse) one enormous file.
- Matches where this codebase is already headed: see the "folder pattern"
  comment in vespa-feeder/flow.py's download_from_s3.

Ad hoc / local run:
    python export_production_snapshot.py --sample-percent 100

As a registered Prefect deployment (see prefect_deploy.py), runs daily via
cron rather than on someone's laptop.
"""

import argparse
import os
import subprocess
import time
from pathlib import Path

import boto3

from prefect import flow, get_run_logger, task

_S3_BUCKET = "cpr-cache"
_S3_PREFIX = "search/vespa/index"
_SHARD_TARGET_BYTES = 200 * 1024 * 1024  # ~200MB per shard, see module docstring


@task
def get_ssm_parameter(name: str) -> str:
    """Read an SSM parameter - same pattern as feed_from_production.py's task of the same name."""
    response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
    value = response["Parameter"].get("Value")
    if value is None:
        raise ValueError(f"SSM parameter {name} has no value")
    return value.strip()


@task(retries=2, retry_delay_seconds=30)
def export_and_shard_from_production(sample_percent: int, workdir: Path) -> list[Path]:
    """Visit the production Vespa application and stream the result into sharded JSONL files of ~_SHARD_TARGET_BYTES each, rather than one large file."""
    logger = get_run_logger()
    shard_dir = workdir / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)

    endpoint = get_ssm_parameter("/search/vespa/endpoint")
    read_token = get_ssm_parameter("/search/vespa/read_token")
    application = get_ssm_parameter("/search/vespa/application")

    cmd = ["vespa", "visit", "--target", endpoint, "--application", application]
    if sample_percent < 100:
        # Hash-based sampling over the document id - see feed_from_production.py.
        cmd += ["--selection", f"id.hash().abs() % 100 < {sample_percent}"]

    logger.info(f"Visiting {application} ({sample_percent}% sample) -> {shard_dir}")
    start = time.perf_counter()

    shard_paths: list[Path] = []
    shard_index = 0
    shard_bytes = 0
    record_count = 0
    shard_path = shard_dir / f"part-{shard_index:05d}.jsonl"
    shard_paths.append(shard_path)
    shard_file = shard_path.open("w")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "VESPA_CLI_DATA_PLANE_TOKEN": read_token},
    )
    if process.stdout is not None:
        for line in process.stdout:
            if not line.strip():
                continue
            shard_file.write(line)
            shard_bytes += len(line)
            record_count += 1
            if shard_bytes >= _SHARD_TARGET_BYTES:
                shard_file.close()
                shard_index += 1
                shard_bytes = 0
                shard_path = shard_dir / f"part-{shard_index:05d}.jsonl"
                shard_paths.append(shard_path)
                shard_file = shard_path.open("w")
    shard_file.close()

    stderr = process.stderr.read() if process.stderr else ""
    returncode = process.wait()
    duration = time.perf_counter() - start

    if returncode != 0:
        logger.error(f"vespa visit failed after {duration:.1f}s: {stderr.strip()}")
        raise subprocess.CalledProcessError(returncode, cmd, stderr=stderr)

    # Drop the trailing shard if the last write landed exactly on a rotation boundary.
    if shard_paths and shard_paths[-1].stat().st_size == 0:
        shard_paths.pop().unlink()

    logger.info(
        f"Visited {record_count} documents in {duration:.1f}s -> "
        f"{len(shard_paths)} shard(s) in {shard_dir}"
    )
    return shard_paths


@task(retries=2, retry_delay_seconds=15)
def upload_shards_to_s3(shard_paths: list[Path]) -> None:
    """
    Upload today's shards to S3, then delete any shards left over from a

    previous run that produced more parts than today's - otherwise a
    shrinking corpus leaves stale part files behind for vespa-feeder to pick
    up alongside the fresh ones.
    """
    logger = get_run_logger()
    s3 = boto3.client("s3")

    for shard_path in shard_paths:
        key = f"{_S3_PREFIX}/{shard_path.name}"
        s3.upload_file(str(shard_path), _S3_BUCKET, key)
        logger.info(f"Uploaded {shard_path} -> s3://{_S3_BUCKET}/{key}")

    keep_names = {shard_path.name for shard_path in shard_paths}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_S3_BUCKET, Prefix=f"{_S3_PREFIX}/"):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key and key.rsplit("/", 1)[-1] not in keep_names:
                logger.info(f"Deleting stale shard s3://{_S3_BUCKET}/{key}")
                s3.delete_object(Bucket=_S3_BUCKET, Key=key)


@flow(name="export-production-snapshot")
def export_production_snapshot(
    sample_percent: int = 100,
    workdir: str = "/tmp/vespa-snapshot",  # nosec B108
):
    """Snapshot `sample_percent`% of production to sharded JSONL on S3."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    shard_paths = export_and_shard_from_production(sample_percent, work)
    upload_shards_to_s3(shard_paths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample-percent",
        type=int,
        default=100,
        help="Percent of production corpus to snapshot (100 = full ~10GB)",
    )
    parser.add_argument("--workdir", default="/tmp/vespa-snapshot")  # nosec B108
    args = parser.parse_args()

    export_production_snapshot(
        sample_percent=args.sample_percent,
        workdir=args.workdir,
    )
