"""
Shared engine behind every vespa-feeder.

flow:
- download a file from S3
- optionally derive data from its records
- feed it to Vespa via the `vespa feed` CLI.

Domain-specific flows (labels_flow.py, documents_flow.py, passages_flow.py)
import `vespa_feeder` and compose it with their own S3 source and (if any)
deriver function. Nothing in this module is domain-specific.
"""

import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from itertools import batched
from pathlib import Path

import boto3
import orjson
from mypy_boto3_s3 import S3Client
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import INPUTS
from prefect.client.schemas.objects import State
from prefect.futures import PrefectFuture
from prefect.states import Failed
from pydantic import BaseModel, ConfigDict, Field
from telemetry import tracer, trace

from prefect import get_run_logger, task

# Per-subprocess connection pool size (see the `--connections` comment in
# vespa_feed). Paired with the flow's own ThreadPoolTaskRunner(max_workers=N)
# - see the submit loop in vespa_feeder: total concurrent connections to Vespa
# is that max_workers * _DEFAULT_CONNECTIONS. Benchmarking (8x2 vs 4x4, same
# total connection budget) found 8x2 ~15% faster, so tune both together rather
# than either in isolation.
_DEFAULT_CONNECTIONS = 2


# How many S3 keys each materialize/feed/delete chain handles at once.
DEFAULT_BATCH_SIZE = 10

# 1 feeds every file list_s3_keys discovers. Lower it to benchmark against a
# subset of a source without needing a separate S3 prefix; production flows
# should leave it alone.
DEFAULT_SAMPLE_RATE = 1.0

# How long
_DEFAULT_VESPA_FEED_TIMEOUT_SECONDS_PER_FILE = 300


@dataclass
class FailedDocument:
    doc_id: str
    error: str


@dataclass
class VespaHTTPError(Exception):
    """Transport layer gave up — no HTTP response received for some records."""

    feeder_error_count: int  # feeder.error.count
    failed_documents: list[FailedDocument]


@dataclass
class VespaResponseError(Exception):
    """HTTP responses received but records still lost after exhausting retries."""

    ok_count: int  # feeder.ok.count
    operation_count: int  # feeder.operation.count
    throttled_count: int  # requests that got a 429 at some point
    other_http_error_count: int  # non-2xx responses other than 429, e.g. 5xx
    failed_documents: list[FailedDocument]


VespaFeedError = VespaHTTPError | VespaResponseError


class VespaFeedResponse(BaseModel):
    """Parses the JSON stats the `vespa feed` CLI prints to stdout."""

    model_config = ConfigDict(populate_by_name=True)

    feeder_operation_count: int = Field(alias="feeder.operation.count", default=0)
    feeder_ok_count: int = Field(alias="feeder.ok.count", default=0)
    feeder_error_count: int = Field(alias="feeder.error.count", default=0)
    # The CLI's own self-measured feed duration - comparing this against our
    # wall-clock time around the subprocess call isolates process spawn/init/
    # connection-setup overhead (ours - theirs) from actual transfer time.
    feeder_seconds: float = Field(alias="feeder.seconds", default=0.0)
    http_response_error_count: int = Field(alias="http.response.error.count", default=0)
    http_response_code_counts: dict[str, int] = Field(
        alias="http.response.code.counts", default_factory=dict
    )


@dataclass
class FeedResult:
    feed_paths: list[Path]
    input_count: int
    operation_count: int
    ok_count: int
    feeder_error_count: int  # transport-layer failures, no HTTP response received
    throttled_count: int  # requests that got a 429 at some point (may have retried ok)
    other_http_error_count: int  # non-2xx responses other than 429, e.g. 5xx
    errors: list[VespaFeedError]


_GIVING_UP_RE = re.compile(r"^feed: (.+) for put (\S+): giving up", re.MULTILINE)


def _parse_failed_documents(stderr: str) -> list[FailedDocument]:
    return [
        FailedDocument(doc_id=giving_up_match.group(2), error=giving_up_match.group(1))
        for giving_up_match in _GIVING_UP_RE.finditer(stderr)
    ]


def _build_run_summary_markdown(
    results: list["FeedResult"], failed_results: list["FeedResult"]
) -> str:
    total_input = sum(r.input_count for r in results)
    total_operation = sum(r.operation_count for r in results)
    total_ok = sum(r.ok_count for r in results)
    total_missing = total_operation - total_ok
    total_feeder_errors = sum(r.feeder_error_count for r in results)
    total_throttled = sum(r.throttled_count for r in results)
    total_other_http_errors = sum(r.other_http_error_count for r in results)
    throttle_rate = total_throttled / total_operation if total_operation else 0.0

    icon = "🚨" if failed_results else "✅"
    status = (
        f"**{len(failed_results)}/{len(results)} file(s) failed**"
        if failed_results
        else "**All files indexed successfully**"
    )

    markdown = (
        f"### Vespa Feeder Run Summary\n\n{icon} {status}\n\n"
        "| Metric | Value |\n|---|---|\n"
        f"| Files processed | {len(results)} |\n"
        f"| Failed files | {len(failed_results)} |\n"
        f"| Input records | {total_input} |\n"
        f"| Operations | {total_operation} |\n"
        f"| OK | {total_ok} |\n"
        f"| **Missing (not recovered after retries)** | **{total_missing}** |\n"
        f"| — | — |\n"
        f"| _Transient, self-resolved (no data lost):_ | |\n"
        f"| Transport retries (feeder errors) | {total_feeder_errors} |\n"
        f"| Throttled (429) | {total_throttled} |\n"
        f"| Other non-2xx responses | {total_other_http_errors} |\n"
        f"| Throttle rate | {throttle_rate:.2%} |\n"
    )

    if failed_results:
        markdown += (
            "\n#### Failed files\n\n"
            "| File | OK / Operation | Missing | Sample failed documents |\n"
            "|---|---|---|---|\n"
        )
        for r in failed_results:
            failed_docs = [doc for error in r.errors for doc in error.failed_documents]
            sample = "; ".join(
                f"`{doc.doc_id}`: {doc.error}" for doc in failed_docs[:3]
            )
            if len(failed_docs) > 3:
                sample += f" (+{len(failed_docs) - 3} more)"
            markdown += (
                f"| `{', '.join(p.name for p in r.feed_paths)}` | "
                f"{r.ok_count}/{r.operation_count} | "
                f"{r.operation_count - r.ok_count} | {sample or '—'} |\n"
            )

    return markdown


def list_s3_keys(bucket: str, key: str) -> list[str]:
    s3: S3Client = boto3.client("s3")

    prefix = key.rstrip("/") + "/"
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
        raise FileNotFoundError(f"No objects found at s3://{bucket}/{key}")

    keys = [obj.get("Key", "") for obj in objects]

    return keys


def get_ssm_parameter(name: str) -> str:
    response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
    value = response["Parameter"].get("Value")
    if value is None:
        raise ValueError(f"SSM parameter {name} has no value")
    return value.strip()


@tracer.start_as_current_span("materialize_s3_files")
def materialize_s3_files(bucket: str, batched_s3_keys: list[str]) -> list[Path]:
    s3: S3Client = boto3.client("s3")

    materialized_s3_files = []
    for s3_key in batched_s3_keys:
        materialized_s3_file = Path(tempfile.gettempdir()) / s3_key.split("/")[-1]
        s3.download_file(bucket, s3_key, str(materialized_s3_file))
        materialized_s3_files.append(materialized_s3_file)

    return materialized_s3_files


@tracer.start_as_current_span("materialize_derived_files")
def materialize_derived_files(
    materialized_s3_files: list[Path],
    derive_data_from_source: Callable[[dict], dict] | None,
) -> list[Path]:
    """
    Write a `.derived` copy of every source file, deriver or no deriver.

    This allows `feed_batch` to delete the S3 sources as soon as this returns.
    """
    derive = derive_data_from_source or (lambda record: record)

    materialized_derived_files = []
    for materialized_s3_file in materialized_s3_files:
        derived_file = materialized_s3_file.with_name(
            f"{materialized_s3_file.stem}.derived{materialized_s3_file.suffix}"
        )
        with materialized_s3_file.open("rb") as src, derived_file.open("wb") as dst:
            for line in src:
                if not line.strip():
                    continue
                record = derive(orjson.loads(line))
                dst.write(orjson.dumps(record) + b"\n")
        materialized_derived_files.append(derived_file)

    return materialized_derived_files


@tracer.start_as_current_span("feed_derived_files")
def feed_derived_files(
    materialized_derived_files: list[Path],
    endpoint: str,
    application: str,
    connections: int = _DEFAULT_CONNECTIONS,
    feed_timeout_seconds_per_file: int = _DEFAULT_VESPA_FEED_TIMEOUT_SECONDS_PER_FILE,
) -> FeedResult:
    input_count = sum(
        1
        for materialized_derived_file in materialized_derived_files
        for line in materialized_derived_file.open("rb")
        if line.strip()
    )

    result = subprocess.run(
        [
            "vespa",
            "feed",
            *[
                str(materialized_derived_file)
                for materialized_derived_file in materialized_derived_files
            ],
            "--target",
            endpoint,
            "--application",
            application,
            "--connections",
            str(connections),
            "--inflight",
            "0",
            "--verbose",
        ],
        env=os.environ,
        capture_output=True,
        text=True,
        timeout=feed_timeout_seconds_per_file * len(materialized_derived_files),
        check=True,
    )

    response = VespaFeedResponse.model_validate(orjson.loads(result.stdout))
    throttled_count = response.http_response_code_counts.get("429", 0)
    other_http_error_count = response.http_response_error_count - throttled_count
    missing_count = response.feeder_operation_count - response.feeder_ok_count
    failed_documents = _parse_failed_documents(result.stderr)

    errors: list[VespaFeedError] = []
    if missing_count > 0:
        if response.feeder_error_count > 0:
            errors.append(
                VespaHTTPError(
                    feeder_error_count=response.feeder_error_count,
                    failed_documents=failed_documents,
                )
            )
        errors.append(
            VespaResponseError(
                ok_count=response.feeder_ok_count,
                operation_count=response.feeder_operation_count,
                throttled_count=throttled_count,
                other_http_error_count=other_http_error_count,
                failed_documents=failed_documents,
            )
        )

    return FeedResult(
        feed_paths=materialized_derived_files,
        input_count=input_count,
        operation_count=response.feeder_operation_count,
        ok_count=response.feeder_ok_count,
        feeder_error_count=response.feeder_error_count,
        throttled_count=throttled_count,
        other_http_error_count=other_http_error_count,
        errors=errors,
    )


@tracer.start_as_current_span("delete_materialized_s3_files")
def delete_materialized_s3_files(materialized_s3_files: list[Path]) -> None:
    for materialized_s3_file in materialized_s3_files:
        materialized_s3_file.unlink(missing_ok=True)


@tracer.start_as_current_span("delete_materialized_derived_files")
def delete_materialized_derived_files(materialized_derived_files: list[Path]) -> None:
    for materialized_derived_file in materialized_derived_files:
        materialized_derived_file.unlink(missing_ok=True)


@tracer.start_as_current_span("feed_batch")
@task(cache_policy=INPUTS - "derive_data_from_source")
def feed_batch(
    endpoint: str,
    application: str,
    connections: int,
    feed_timeout_seconds_per_file: int,
    s3_bucket: str,
    batched_s3_keys: tuple[str, ...],
    derive_data_from_source: Callable[[dict], dict] | None = None,
) -> FeedResult:
    materialized_s3_files = materialize_s3_files(
        bucket=s3_bucket, batched_s3_keys=list(batched_s3_keys)
    )

    materialized_derived_files = materialize_derived_files(
        materialized_s3_files=materialized_s3_files,
        derive_data_from_source=derive_data_from_source,
    )

    # Halves peak disk - a batch otherwise holds both sets at once.
    delete_materialized_s3_files(materialized_s3_files=materialized_s3_files)

    try:
        return feed_derived_files(
            materialized_derived_files=materialized_derived_files,
            endpoint=endpoint,
            application=application,
            connections=connections,
            feed_timeout_seconds_per_file=feed_timeout_seconds_per_file,
        )
    finally:
        delete_materialized_derived_files(
            materialized_derived_files=materialized_derived_files
        )


@tracer.start_as_current_span("vespa_feeder_v2")
def vespa_feeder_v2(
    s3_bucket: str,
    s3_key: str,
    derive_data_from_source: Callable[[dict], dict] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    connections: int = _DEFAULT_CONNECTIONS,
    feed_timeout_seconds_per_file: int = _DEFAULT_VESPA_FEED_TIMEOUT_SECONDS_PER_FILE,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
) -> State | None:
    run_logger = get_run_logger()

    if not 0 < sample_rate <= 1:
        raise ValueError(f"sample_rate must be in (0, 1], got {sample_rate}")

    endpoint = get_ssm_parameter(name="/search/vespa/endpoint")
    application = get_ssm_parameter(name="/search/vespa/application")
    # This is read by Vespa CLI
    # @see: https://docs.vespa.ai/en/security/guide.html#use-endpoints
    os.environ["VESPA_CLI_DATA_PLANE_TOKEN"] = get_ssm_parameter(
        name="/search/vespa/write_token"
    )

    s3_keys = list_s3_keys(bucket=s3_bucket, key=s3_key)
    if sample_rate < 1:
        # Every nth key from the sorted listing, rather than the first n. Both
        # are deterministic - so every A/B variant feeds the identical subset -
        # but a stride is positionally unbiased, which matters if whatever
        # produced the files varies along the ordering.
        s3_keys = s3_keys[:: round(1 / sample_rate)]

    # Log and trace before we get going
    run_logger.info(
        f"Feeding {len(s3_keys)} files from s3://{s3_bucket}/{s3_key} "
        f"in batches of {batch_size} (sample_rate={sample_rate})"
    )
    trace.get_current_span().set_attributes(
        {
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "batch_size": batch_size,
            "sample_rate": sample_rate,
            "connections": connections,
            "s3_keys_len": len(s3_keys),
        }
    )

    s3_key_batches = list(batched(s3_keys, batch_size))

    feed_futures: list[PrefectFuture[FeedResult]] = []
    for batch_number, batched_s3_keys in enumerate(s3_key_batches, start=1):
        run_logger.info(
            f"Feeding batch {batch_number}/{len(s3_key_batches)} "
            f"({len(batched_s3_keys)} files)"
        )
        feed_futures.append(
            feed_batch.submit(
                endpoint=endpoint,
                application=application,
                connections=connections,
                feed_timeout_seconds_per_file=feed_timeout_seconds_per_file,
                s3_bucket=s3_bucket,
                batched_s3_keys=batched_s3_keys,
                derive_data_from_source=derive_data_from_source,
            )
        )

    results = []
    for feed_future in feed_futures:
        feed_result = feed_future.result()
        run_logger.info(
            f"Fed {len(feed_result.feed_paths)} file(s): "
            f"input={feed_result.input_count} "
            f"operation={feed_result.operation_count} ok={feed_result.ok_count} "
            f"missing={feed_result.operation_count - feed_result.ok_count} "
            f"throttled={feed_result.throttled_count}"
        )
        results.append(feed_result)

    failed_results = [result for result in results if result.errors]

    create_markdown_artifact(
        key="vespa-feeder-run-summary",
        markdown=_build_run_summary_markdown(results, failed_results),
        description="Aggregate summary of the vespa-feeder run across all files",
    )

    if failed_results:
        failed_paths = ", ".join(
            str(feed_path)
            for result in failed_results
            for feed_path in result.feed_paths
        )
        return Failed(
            message=(
                f"vespa_feed: failed for {len(failed_results)}/{len(results)} "
                f"batch(es): {failed_paths}. See the vespa-feeder-run-summary "
                "artifact and per-batch error logs above for details."
            )
        )
