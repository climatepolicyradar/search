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
    prefect deployment run 'search-vespa-dev-feed-from-production/<deployment-name>' \
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
  fixed 100% dump - see download_shard's docstring.
- Downloads and feeds one shard at a time, deleting each as soon as it's fed,
  rather than downloading the whole snapshot up front. This mirrors
  export_production_snapshot.py's upload_and_remove_shard, for the same
  reason: the snapshot is ~75GiB as of 2026-08-11 and grows with the corpus,
  so holding it all locally meant sizing the ECS task's ephemeral storage to
  the whole corpus and re-raising it every time production grew. One shard at
  a time is ~200MB no matter how large the corpus gets.

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

# Matches the parent document id a snapshot line belongs to. A `documents`
# line carries it as its own id; a `passages` line carries the same value in
# its `document_ref` field, e.g.
#   {"id":"id:passages:passages::<uuid>",
#    "fields":{"document_ref":"id:documents:documents::<parent>", ...}}
# so hashing on this match samples a document and its passages *together*
# rather than feeding passages whose parent document was dropped.
#
# `labels` lines match nothing here - see download_shard on why they're kept
# whole rather than sampled.
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
def list_snapshot_shards() -> list[str]:
    """
    List the daily production snapshot's shard keys in S3.

    Sorted (part-00000, part-00001, ...) so a run's progress through the
    corpus is legible in the logs, and so a run that dies partway through
    says unambiguously how far it got.
    """
    logger = get_run_logger()
    prefix = f"{_SNAPSHOT_S3_PREFIX}/"
    paginator = boto3.client("s3").get_paginator("list_objects_v2")
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
        f"Found {len(keys)} snapshot shard(s) at s3://{_SNAPSHOT_S3_BUCKET}/{prefix}"
    )
    return keys


@task(retries=2, retry_delay_seconds=30)
def download_shard(key: str, workdir: Path, sample_percent: int) -> Path:
    """Download one snapshot shard, and return its path"""
    logger = get_run_logger()
    name = key.rsplit("/", 1)[-1]

    raw_dir = workdir / "snapshot"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / name
    boto3.client("s3").download_file(_SNAPSHOT_S3_BUCKET, key, str(raw_path))

    if sample_percent >= 100:
        return raw_path

    sampled_dir = workdir / "sampled"
    sampled_dir.mkdir(parents=True, exist_ok=True)
    sampled_path = sampled_dir / name
    record_count = 0
    reference_count = 0
    with raw_path.open("r") as src, sampled_path.open("w") as dst:
        for line in src:
            match = _DOC_ID_RE.search(line)
            if match is None:
                # Standalone reference data (the `labels` schema): not tied to
                # any document, so there's no parent id to sample it by, and
                # it's ~0.2% of the corpus. Keep all of it - the previous
                # `if match and ...` dropped every labels document at any
                # sample_percent < 100, leaving dev instances with none.
                dst.write(line)
                reference_count += 1
            elif zlib.crc32(match.group(1).encode()) % 100 < sample_percent:
                dst.write(line)
                record_count += 1
    raw_path.unlink()
    logger.info(
        f"Sampled {record_count} documents ({sample_percent}%) from {name}, "
        f"kept {reference_count} unsampled reference document(s)"
    )

    return sampled_path


@task(retries=3, retry_delay_seconds=30)
def feed_and_remove_shard(target: str, shard_path: Path) -> int:
    """
    Feed one downloaded snapshot shard into the target instance, then delete the local copy.

    Deleting as soon as the shard is fed - rather than after the whole corpus
    has been fed - is what keeps local disk bounded to roughly one shard
    instead of the full snapshot (see the module docstring). The unlink sits
    inside this task so it can only happen after a successful feed: a retry
    re-feeds a file that's still on disk.

    Returns the number of documents successfully fed, so the flow can report a
    corpus-wide total rather than leaving you to add up 382 per-shard lines.

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

    logger.info(f"Feeding {shard_path} into {target}")
    start = time.perf_counter()
    result = subprocess.run(
        [
            "vespa",
            "feed",
            "--target",
            endpoint,
            "--application",
            target,
            str(shard_path),
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
    shard_path.unlink()
    logger.info(
        f"Fed {ok_count}/{operation_count} documents into {target} in {duration:.1f}s "
        f"(errors={error_count}, response codes={response_code_counts}), "
        f"local copy removed"
    )

    return ok_count


@flow(name="search-vespa-dev-feed-from-production")
def feed_from_production(
    target: str,
    sample_percent: int = 5,
    workdir: str = "/tmp/vespa-feed",  # nosec B108
):
    """Feed `target` (tenant.application.instance) from a sample of the daily production snapshot."""
    logger = get_run_logger()
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    # get the keys of the shards
    keys = list_snapshot_shards()

    start = time.perf_counter()
    fed_count = 0
    for index, key in enumerate(keys, start=1):
        # download the shard to workdir, and return the path
        shard_path = download_shard(key, work, sample_percent)
        # feed and remove the workdir/shard_path
        fed_count += feed_and_remove_shard(target, shard_path)
        logger.info(
            f"Shard {index}/{len(keys)} done ({fed_count} documents fed so far)"
        )

    logger.info(
        f"Fed {fed_count} documents from {len(keys)} shard(s) into {target} "
        f"in {time.perf_counter() - start:.1f}s"
    )


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
        help="Percent of production corpus to feed (100 = full ~75GiB)",
    )
    parser.add_argument("--workdir", default="/tmp/vespa-feed")  # nosec B108
    args = parser.parse_args()

    feed_from_production(
        target=args.target,
        sample_percent=args.sample_percent,
        workdir=args.workdir,
    )
