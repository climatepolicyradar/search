"""
Prefect flow: feed a Vespa Cloud instance from a sample of the production corpus.

Creating and deploying the app (`just create` / `just deploy`) are plain
`vespa` CLI calls in the justfile - no Python involved there. This flow only
covers the feed step, since that's the long-running, failure-prone part of
the workflow (a potentially multi-GB download+feed), so it's worth wrapping
it in something with retries/logging - and, once registered as a deployment,
worth running on a cloud worker instead of a laptop. It is not needed to
orchestrate "deploy the app" - that stays a single `vespa deploy` call.

Ad hoc / local run (executes wherever you invoke it):
    python feed_from_production.py \
        --target climate-policy-radar.search-dev.jamesgorrie \
        --sample-percent 5

As a registered Prefect deployment (executes on a worker instead of your
laptop - worth setting up once this runs often, or before a full 100% feed):
    prefect deploy
    prefect deployment run 'feed-from-production/<deployment-name>' \
        -p target=... -p sample_percent=100

Design notes
------------
- Shells out to `vespa feed` rather than reimplementing the Document API -
  keeps this in lockstep with whatever the CLI supports (retries,
  compression) and matches what's documented at
  https://docs.vespa.ai/en/operations/cloning.html#cloning---vespa-cloud-to-self-hosted
- Passes -a/-t explicitly on every call instead of mutating global state via
  `vespa config set` - two engineers (or two runs) can safely feed different
  instances at the same time without stomping on each other's CLI config.
- Reads from the daily production snapshot at s3://cpr-cache/search/vespa/index/
  (see export_production_snapshot.py) rather than visiting production
  directly on every run. That used to be the case, but it put a `vespa visit`
  read load on production on every feed and required every engineer to hold
  production data-plane read credentials - reading a snapshot that's already
  in S3 is cheaper on production, faster per engineer, and needs no direct
  production credentials for everyone doing relevance work.
- Sampling happens locally against the snapshot rather than via the document
  selector language's hash-based pattern, since the snapshot itself is a
  fixed 100% dump - see download_snapshot's docstring.

Important caveat on where this actually runs: invoking this as a plain
`python` script (what `just feed` does) executes the flow *locally*, on
whatever machine ran it. That's fine for a small sample, but a full 100% feed
should go through a registered Prefect deployment on a cloud-hosted work pool
rather than a laptop, or you're back to the original "multi-GB transfer over
home wifi" problem this workflow exists to avoid.
"""

import argparse
import json
import os
import re
import subprocess
import time
import zlib
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from prefect import flow, get_run_logger, task

_SNAPSHOT_S3_BUCKET = "cpr-cache"
_SNAPSHOT_S3_PREFIX = "search/vespa/index"

# Matches the document id out of a `vespa visit` put/update operation, e.g.
# {"put": "id:documents:documents::<id>", ...} - see export_production_snapshot.py.
_DOC_ID_RE = re.compile(r'"id:documents:documents::([^"]+)"')


@task
def get_ssm_parameter(name: str) -> str:
    """Read an SSM parameter - used to resolve the dev instance's endpoint/write token."""
    client = boto3.client("ssm")
    try:
        response = client.get_parameter(Name=name, WithDecryption=True)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ParameterNotFound":
            raise RuntimeError(
                f"SSM parameter {name} not found in region {client.meta.region_name}. "
                "For a per-instance endpoint (/search/vespa-dev/<instance>), run "
                "`just create <instance>` first (in the production account, eu-west-1)."
            ) from exc
        raise
    value = response["Parameter"].get("Value")
    if value is None:
        raise ValueError(f"SSM parameter {name} has no value")
    return value.strip()


@task(retries=2, retry_delay_seconds=30)
def download_snapshot(sample_percent: int, workdir: Path) -> list[Path]:
    """
    Download the daily production snapshot's shards from S3.

    If sample_percent < 100, locally downsample them by document id.

    The snapshot is always a full (100%) dump, so unlike the old
    `vespa visit --selection` approach, sampling can't happen server-side
    here - instead each downloaded shard is filtered by a stable hash of the
    document id (`crc32(id) % 100 < sample_percent`). This doesn't need to
    match Vespa's own `id.hash()` selector exactly - it just needs to be a
    deterministic, roughly-uniform subset for fast day-to-day iteration.
    Pass --sample-percent 100 for a full-corpus feed before a final relevance
    evaluation.
    """
    logger = get_run_logger()
    s3 = boto3.client("s3")

    snapshot_dir = workdir / "snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{_SNAPSHOT_S3_PREFIX}/"
    paginator = s3.get_paginator("list_objects_v2")
    keys = sorted(
        key
        for page in paginator.paginate(Bucket=_SNAPSHOT_S3_BUCKET, Prefix=prefix)
        for obj in page.get("Contents", [])
        if (key := obj.get("Key", "")).endswith(".jsonl")
    )
    if not keys:
        raise FileNotFoundError(
            f"No snapshot shards found at s3://{_SNAPSHOT_S3_BUCKET}/{prefix} - "
            "has export_production_snapshot run yet?"
        )

    logger.info(
        f"Downloading {len(keys)} snapshot shard(s) from s3://{_SNAPSHOT_S3_BUCKET}/{prefix}"
    )
    start = time.perf_counter()
    shard_paths = []
    for key in keys:
        shard_path = snapshot_dir / key.rsplit("/", 1)[-1]
        s3.download_file(_SNAPSHOT_S3_BUCKET, key, str(shard_path))
        shard_paths.append(shard_path)
    logger.info(
        f"Downloaded {len(shard_paths)} shard(s) in {time.perf_counter() - start:.1f}s"
    )

    if sample_percent >= 100:
        return shard_paths

    sampled_dir = workdir / "sampled"
    sampled_dir.mkdir(parents=True, exist_ok=True)
    sampled_paths = []
    record_count = 0
    for shard_path in shard_paths:
        sampled_path = sampled_dir / shard_path.name
        with shard_path.open("r") as src, sampled_path.open("w") as dst:
            for line in src:
                match = _DOC_ID_RE.search(line)
                if match and zlib.crc32(match.group(1).encode()) % 100 < sample_percent:
                    dst.write(line)
                    record_count += 1
        sampled_paths.append(sampled_path)
    logger.info(
        f"Sampled {record_count} documents ({sample_percent}%) across "
        f"{len(sampled_paths)} shard(s) -> {sampled_dir}"
    )

    return sampled_paths


@task(retries=3, retry_delay_seconds=30)
def feed_target(target: str, corpus_file: Path) -> None:
    """
    Feed one downloaded snapshot shard into the target instance.

    Personal dev instances get a fresh, unpredictable endpoint URL on every
    `just create`, so unlike the snapshot's S3 location we can't hardcode one
    fixed value here. `just create` resolves it and stores it in SSM under
    /search/vespa-dev/<instance> (see vespa-dev/justfile) - we read it
    from there rather than resolving it ourselves via `-a/-t cloud`, which
    would need Vespa Cloud control-plane credentials that aren't available
    on a Prefect worker.
    """
    logger = get_run_logger()
    instance = target.rsplit(".", 1)[-1]

    endpoint = get_ssm_parameter(f"/search/vespa-dev/{instance}")
    write_token = get_ssm_parameter("/search/vespa-dev/write_token")

    logger.info(f"Feeding {corpus_file} into {target}")
    start = time.perf_counter()
    result = subprocess.run(
        [
            "vespa",
            "feed",
            "--target",
            endpoint,
            "--application",
            target,
            str(corpus_file),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "VESPA_CLI_DATA_PLANE_TOKEN": write_token},
    )
    duration = time.perf_counter() - start
    if result.returncode != 0:
        logger.error(
            f"vespa feed failed after {duration:.1f}s: {result.stderr.strip()}"
        )
        result.check_returncode()

    summary = json.loads(result.stdout)
    operation_count = summary.get("feeder.operation.count", 0)
    ok_count = summary.get("feeder.ok.count", 0)
    error_count = summary.get("feeder.error.count", 0)
    response_code_counts = summary.get("http.response.code.counts", {})
    logger.info(
        f"Fed {ok_count}/{operation_count} documents into {target} in {duration:.1f}s "
        f"(errors={error_count}, response codes={response_code_counts})"
    )


@flow(name="feed-from-production")
def feed_from_production(
    target: str,
    sample_percent: int = 5,
    workdir: str = "/tmp/vespa-feed",  # nosec B108
):
    """Feed `target` (tenant.application.instance) from a sample of the daily production snapshot."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    shard_paths = download_snapshot(sample_percent, work)
    for shard_path in shard_paths:
        feed_target(target, shard_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        required=True,
        help="tenant.application.instance to feed, e.g. climate-policy-radar.search-dev.<username>",
    )
    parser.add_argument(
        "--sample-percent",
        type=int,
        default=5,
        help="Percent of production corpus to feed (100 = full ~10GB)",
    )
    parser.add_argument("--workdir", default="/tmp/vespa-feed")  # nosec B108
    args = parser.parse_args()

    feed_from_production(
        target=args.target,
        sample_percent=args.sample_percent,
        workdir=args.workdir,
    )
