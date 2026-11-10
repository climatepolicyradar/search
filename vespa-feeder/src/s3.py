"""
Getting the data in and out of S3, and the bounds on doing so.

Discovery, download and SSM lookups, plus the derive step that writes the
`.derived` copies the feed reads. Split from `vespa_feeder` so the flow module
holds the feeding itself; nothing here knows about Vespa.

`vespa_feeder` re-exports these, so `feeder.list_s3_keys`, `feeder._BOTO_CONFIG`
and friends keep resolving for the tests that reach for them.
"""

import re
import time
from collections.abc import Callable
from pathlib import Path

import boto3
import orjson
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from mypy_boto3_s3 import S3Client
from telemetry import tracer

# Socket-level bounds for every S3/SSM call.
#
# Measured over 24h: `materialise_s3_files` p50 1.3s, p99 8.4s, max 17s. These
# are generous multiples of that, so they never fire in normal operation and
# only catch a genuinely wedged socket. boto3's own defaults are 60s, but they
# sit under a retry layer that can extend a stalled call indefinitely.
#
# This is a socket timeout rather than a wrapper around the call because the
# task runs on a ThreadPoolTaskRunner worker, where Prefect cannot interrupt
# blocking I/O -- a wrapper would not actually interrupt anything.
_S3_CONNECT_TIMEOUT_SECONDS = 10
_S3_READ_TIMEOUT_SECONDS = 120

_BOTO_CONFIG = Config(
    connect_timeout=_S3_CONNECT_TIMEOUT_SECONDS,
    read_timeout=_S3_READ_TIMEOUT_SECONDS,
    retries={"max_attempts": 3, "mode": "standard"},
)

# How long the whole download phase of one batch may take.
#
# The socket timeouts above bound a single read, not the operation:
# `download_file` is the S3 Transfer Manager, whose own `num_download_attempts`
# (5) nests OUTSIDE botocore's `max_attempts` (3), each able to restart a
# stalled stream. Run 06aec620 wedged all 8 workers here for 52h with both
# bounds in place, so only a deadline across the phase actually bounds it.
#
# Measured over 24h: p50 1.3s, p99 8.4s, max 17s for a 10-file batch, so 5 min
# never fires in normal operation.
_S3_DOWNLOAD_TIMEOUT_SECONDS = 5 * 60

# Keeps every download on the calling worker thread, which is what makes a
# stalled one visible: behind the Transfer Manager's pool the worker blocks on
# a future while 10 pool threads retry underneath it, where neither the socket
# timeouts nor the deadline above can see it. Per-file latency gives the
# concurrency nothing to buy here anyway.
_S3_TRANSFER_CONFIG = TransferConfig(use_threads=False)


_EXPORT_NAME_RE = re.compile(r"^\d{8}T\d{6}Z$")


def get_latest_s3_export_prefix(bucket: str, prefix: str) -> str:
    """
    The newest immutable snapshot under `prefix`, e.g. `20260922T190625Z`.

    `/latest` is mutable which can, and has, been mutated during a run
    causing S3 404 errors.

    These keys are generated in the data-lake
    @see: https://github.com/climatepolicyradar/data-lake/blob/bac07d00c9d799efa126e245accad590d4a0d1e5/orchestration/flows/data_export.py#L106
    """
    s3: S3Client = boto3.client("s3", config=_BOTO_CONFIG)

    paginator = s3.get_paginator("list_objects_v2")
    export_names = sorted(
        (
            common_prefix.get("Prefix", "").removeprefix(prefix).removesuffix("/")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/")
            # because of `Delimiter`, we get `CommonPrefixes` returned as an aggregation
            # e.g. { "CommonPrefixes": [
            #   "production/published/pipeline_data_in_vespa_documents_updates_v1/20260630T082046Z",
            #   "production/published/pipeline_data_in_vespa_documents_updates_v1/20260714T103748Z",
            #   ...
            #   "production/published/pipeline_data_in_vespa_documents_updates_v1/latest",
            # ]}
            #
            # `CommonPrefixes` has a `MaxKeys` of 1000 - which, given this buckets expires objects
            # every 90 days, has very little risk of us hitting that.
            for common_prefix in page.get("CommonPrefixes", [])
        ),
        reverse=True,
    )
    for export_name in export_names:
        # we check for a timestamp in case there are other rogue values or `latest`
        if _EXPORT_NAME_RE.match(export_name):
            return export_name

    raise FileNotFoundError(
        f"No timestamped snapshots found under s3://{bucket}/{prefix}"
    )


def list_s3_keys(bucket: str, prefix: str) -> list[str]:
    s3: S3Client = boto3.client("s3", config=_BOTO_CONFIG)

    prefix = prefix.rstrip("/") + "/"
    paginator = s3.get_paginator("list_objects_v2")
    objects = sorted(
        [
            obj
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
        ],
        key=lambda obj: obj.get("Key", ""),
    )
    if not objects:
        raise FileNotFoundError(f"No objects found at s3://{bucket}/{prefix}")

    keys = [obj.get("Key", "") for obj in objects]

    return keys


def get_ssm_parameter(name: str) -> str:
    response = boto3.client("ssm", config=_BOTO_CONFIG).get_parameter(
        Name=name, WithDecryption=True
    )
    value = response["Parameter"].get("Value")
    if value is None:
        raise ValueError(f"SSM parameter {name} has no value")
    return value.strip()


@tracer.start_as_current_span("materialise_s3_files")
def materialise_s3_files(
    bucket: str,
    batched_s3_keys: list[str],
    materialise_dir: Path,
    download_timeout_seconds: float = _S3_DOWNLOAD_TIMEOUT_SECONDS,
) -> list[Path]:
    s3: S3Client = boto3.client("s3", config=_BOTO_CONFIG)

    # Checked between files, not enforced on each: this runs on a
    # ThreadPoolTaskRunner worker, where Prefect cannot interrupt blocking I/O,
    # so nothing here can abort a download under way - only refuse the next.
    # The socket timeouts bound a single file; this bounds the batch.
    deadline = time.monotonic() + download_timeout_seconds

    materialised_s3_files = []
    for s3_key in batched_s3_keys:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Timed out after {download_timeout_seconds:.0f}s downloading "
                f"{len(batched_s3_keys)} file(s) from s3://{bucket}: "
                f"{len(materialised_s3_files)} done, stopped before {s3_key}"
            )
        materialised_s3_file = materialise_dir / s3_key.split("/")[-1]
        s3.download_file(
            bucket, s3_key, str(materialised_s3_file), Config=_S3_TRANSFER_CONFIG
        )
        materialised_s3_files.append(materialised_s3_file)

    return materialised_s3_files


@tracer.start_as_current_span("materialise_derived_files")
def materialise_derived_files(
    materialised_s3_files: list[Path],
    derive_data_from_source: Callable[[dict], dict] | None,
) -> list[Path]:
    """
    Write a `.derived` copy of every source file, deriver or no deriver.

    This allows `feed_batch` to delete the S3 sources as soon as this returns.
    """
    derive = derive_data_from_source or (lambda record: record)

    materialised_derived_files = []
    for materialised_s3_file in materialised_s3_files:
        derived_file = materialised_s3_file.with_name(
            f"{materialised_s3_file.stem}.derived{materialised_s3_file.suffix}"
        )
        with materialised_s3_file.open("rb") as src, derived_file.open("wb") as dst:
            for line in src:
                if not line.strip():
                    continue
                record = derive(orjson.loads(line))
                dst.write(orjson.dumps(record) + b"\n")
        materialised_derived_files.append(derived_file)

    return materialised_derived_files


@tracer.start_as_current_span("delete_materialised_s3_files")
def delete_materialised_s3_files(materialised_s3_files: list[Path]) -> None:
    for materialised_s3_file in materialised_s3_files:
        materialised_s3_file.unlink(missing_ok=True)


# Caching here would be wrong. A batch with failed documents
# returns a `FeedResult` and finishes Completed, so it
# would cache as a success and never be re-fed.
