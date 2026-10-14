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

import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from types import FrameType

import boto3
import orjson
from mypy_boto3_s3 import S3Client
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import NO_CACHE
from prefect.futures import PrefectFuture
from pydantic import BaseModel, ConfigDict, Field
from telemetry import trace, tracer

from prefect import get_run_logger, task

logger = logging.getLogger(__name__)

# Per-subprocess connection pool size (see the `--connections` comment in
# vespa_feed). Paired with the flow's own ThreadPoolTaskRunner(max_workers=N)
# - see the submit loop in vespa_feeder: total concurrent connections to Vespa
# is that max_workers * _DEFAULT_CONNECTIONS. Benchmarking (8x2 vs 4x4, same
# total connection budget) found 8x2 ~15% faster, so tune both together rather
# than either in isolation.
_DEFAULT_CONNECTIONS = 2


# How many S3 keys each materialise/feed/delete chain handles at once.
DEFAULT_BATCH_SIZE = 10

# 1 feeds every file list_s3_keys discovers. Lower it to benchmark against a
# subset of a source without needing a separate S3 prefix; production flows
# should leave it alone.
DEFAULT_SAMPLE_RATE = 1.0

# How long
_DEFAULT_VESPA_FEED_TIMEOUT_SECONDS_PER_FILE = 300


# we store all `vespa feed` processes in this set to be able to
# terminate them on SIGTERM of the main thread
_vespa_feed_processes: set[subprocess.Popen] = set()
# we use the `_vespa_feed_processes_lock` to `add` or `discard` or read the processes on `_vespa_feed_processes`
_vespa_feed_processes_lock = threading.Lock()
# we store this value to be able to run it on `_terminate_vespa_feed_processes` to avoid
# swallowing any `TerminationSignals`
_main_thread_sigterm_handler: Callable | int | None = None


def _terminate_vespa_feed_processes(signum: int, frame: FrameType | None) -> None:
    with _vespa_feed_processes_lock:
        processes = list(_vespa_feed_processes)
    # A module-level logger rather than get_run_logger(): this runs inside a
    # signal handler, which can re-enter whatever the interrupted frame held.
    logger.warning(
        f"Received signal {signum}, terminating {len(processes)} "
        "in-flight vespa feed process(es)"
    )
    for process in processes:
        process.terminate()

    # Hand back to the handler we displaced - under a flow run that is
    # Prefect's own SIGTERM bridge, which raises TerminationSignal and drives
    # the run to Cancelled. Returning here instead swallows the signal: the
    # flow keeps submitting batches and never reports the cancellation.
    if callable(_main_thread_sigterm_handler):
        _main_thread_sigterm_handler(signum, frame)


def _terminate_vespa_feed_processes_on_sigterm_handler() -> None:
    """
    Runs `_terminate_vespa_feed_processes` on the main threads `SIGTERM`.

    This avoids any unhandled `_vespa_feed_processes`.

    Calling this from vespa_feeder rather than at import time keeps it in
    the Prefect process running the flow.
    """

    global _main_thread_sigterm_handler
    # The conditional guards as signal.signal() raises ValueError outside
    # the main thread.
    #
    # Prefect's runner can re-import this module from a worker thread (e.g. to resolve
    # on_crashed hooks after the flow run's own process has already died).
    if threading.current_thread() is threading.main_thread():
        _main_thread_sigterm_handler = signal.signal(
            signal.SIGTERM, _terminate_vespa_feed_processes
        )


@dataclass
class FailedDocument:
    doc_id: str
    error: str


@dataclass
class VespaFeedError:
    """Transport layer gave up — no HTTP response received for some records."""

    feeder_error_count: int  # feeder.error.count
    failed_documents: list[FailedDocument]


@dataclass
class VespaResponseError:
    """HTTP responses received but records still lost after exhausting retries."""

    ok_count: int  # feeder.ok.count
    operation_count: int  # feeder.operation.count
    throttled_count: int  # requests that got a 429 at some point
    other_http_error_count: int  # non-2xx responses other than 429, e.g. 5xx
    failed_documents: list[FailedDocument]


VespaError = VespaFeedError | VespaResponseError


class VespaFeederFailed(Exception):
    """Records were lost: `vespa feed` never recovered them, or a batch raised."""

    def __init__(
        self,
        message: str,
        failed_results: list["FeedResult"],
        crashes: list[BaseException] | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_results = failed_results
        self.crashes = crashes or []

    def __reduce__(self):
        """
        Without this, unpickling calls __init__ with `args`, which holds only the message

        Prefect pickles exceptions to persist a failed run.
        """
        return (self.__class__, (str(self), self.failed_results, self.crashes))


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
    errors: list[VespaError]


_GIVING_UP_RE = re.compile(r"^feed: (.+) for put (\S+): giving up", re.MULTILINE)


def _parse_failed_documents(stderr: str) -> list[FailedDocument]:
    return [
        FailedDocument(doc_id=giving_up_match.group(2), error=giving_up_match.group(1))
        for giving_up_match in _GIVING_UP_RE.finditer(stderr)
    ]


def _build_run_summary_markdown(
    successes: list["FeedResult"],
    failures: list["FeedResult"],
    exceptions: list[BaseException],
) -> str:
    total_input = sum(r.input_count for r in successes)
    total_operation = sum(r.operation_count for r in successes)
    total_ok = sum(r.ok_count for r in successes)
    total_missing = total_operation - total_ok
    total_feeder_errors = sum(r.feeder_error_count for r in successes)
    total_throttled = sum(r.throttled_count for r in successes)
    total_other_http_errors = sum(r.other_http_error_count for r in successes)
    throttle_rate = total_throttled / total_operation if total_operation else 0.0

    icon = "🚨" if failures or exceptions else "✅"
    status = (
        f"**{len(failures) + len(exceptions)}/{len(successes) + len(exceptions)} "
        "batch(es) failed**"
        if failures or exceptions
        else "**All files indexed successfully**"
    )

    markdown = (
        f"### Vespa Feeder Run Summary\n\n{icon} {status}\n\n"
        "| Metric | Value |\n|---|---|\n"
        f"| Files processed | {len(successes)} |\n"
        f"| Failed files | {len(failures)} |\n"
        f"| Batches that raised | {len(exceptions)} |\n"
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

    if failures:
        markdown += (
            "\n#### Failed files\n\n"
            "| File | OK / Operation | Missing | Sample failed documents |\n"
            "|---|---|---|---|\n"
        )
        for r in failures:
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

    if exceptions:
        markdown += (
            "\n#### Batches that raised\n\n"
            "These never reported a result, so their records were not fed.\n\n"
            "| Exception | Message |\n|---|---|\n"
        )
        for exception in exceptions:
            detail = str(exception).replace("|", "\\|").replace("\n", " ")
            markdown += f"| `{type(exception).__name__}` | {detail} |\n"

    return markdown


_EXPORT_NAME_RE = re.compile(r"^\d{8}T\d{6}Z$")


def get_latest_s3_export_prefix(bucket: str, prefix: str) -> str:
    """
    The newest immutable snapshot under `prefix`, e.g. `20260922T190625Z`.

    `/latest` is mutable which can, and has, been mutated during a run
    causing S3 404 errors.

    These keys are generated in the data-lake
    @see: https://github.com/climatepolicyradar/data-lake/blob/bac07d00c9d799efa126e245accad590d4a0d1e5/orchestration/flows/data_export.py#L106
    """
    s3: S3Client = boto3.client("s3")

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
    s3: S3Client = boto3.client("s3")

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
    response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
    value = response["Parameter"].get("Value")
    if value is None:
        raise ValueError(f"SSM parameter {name} has no value")
    return value.strip()


@tracer.start_as_current_span("materialise_s3_files")
def materialise_s3_files(
    bucket: str, batched_s3_keys: list[str], materialise_dir: Path
) -> list[Path]:
    s3: S3Client = boto3.client("s3")

    materialised_s3_files = []
    for s3_key in batched_s3_keys:
        materialised_s3_file = materialise_dir / s3_key.split("/")[-1]
        s3.download_file(bucket, s3_key, str(materialised_s3_file))
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


@tracer.start_as_current_span("feed_derived_files")
def feed_derived_files(
    materialised_derived_files: list[Path],
    endpoint: str,
    application: str,
    connections: int = _DEFAULT_CONNECTIONS,
    feed_timeout_seconds_per_file: int = _DEFAULT_VESPA_FEED_TIMEOUT_SECONDS_PER_FILE,
) -> FeedResult:
    input_count = sum(
        1
        for materialised_derived_file in materialised_derived_files
        for line in materialised_derived_file.open("rb")
        if line.strip()
    )

    # Popen rather than subprocess.run so _terminate_vespa_feed_processes has
    # something to terminate: run() owns its child privately, and this call is
    # on a task runner worker thread, where a signal handler never runs.
    with subprocess.Popen(
        [
            "vespa",
            "feed",
            *[
                str(materialised_derived_file)
                for materialised_derived_file in materialised_derived_files
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        with _vespa_feed_processes_lock:
            _vespa_feed_processes.add(process)
        try:
            stdout, stderr = process.communicate(
                timeout=feed_timeout_seconds_per_file * len(materialised_derived_files)
            )
        except BaseException:
            # What subprocess.run does too: never leave the child running when
            # the call that owns it is unwinding. Popen.__exit__ then closes
            # the pipes and reaps it.
            process.kill()
            raise
        finally:
            with _vespa_feed_processes_lock:
                _vespa_feed_processes.discard(process)

    # replicates the `check=True` from `subprocess.run()`
    # as we use `Popen` above.
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, process.args, output=stdout, stderr=stderr
        )

    response = VespaFeedResponse.model_validate(orjson.loads(stdout))
    throttled_count = response.http_response_code_counts.get("429", 0)
    other_http_error_count = response.http_response_error_count - throttled_count
    not_ok_count = response.feeder_operation_count - response.feeder_ok_count
    failed_documents = _parse_failed_documents(stderr)

    errors: list[VespaError] = []
    if not_ok_count > 0:
        if response.feeder_error_count > 0:
            errors.append(
                VespaFeedError(
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
        feed_paths=materialised_derived_files,
        input_count=input_count,
        operation_count=response.feeder_operation_count,
        ok_count=response.feeder_ok_count,
        feeder_error_count=response.feeder_error_count,
        throttled_count=throttled_count,
        other_http_error_count=other_http_error_count,
        errors=errors,
    )


@tracer.start_as_current_span("delete_materialised_s3_files")
def delete_materialised_s3_files(materialised_s3_files: list[Path]) -> None:
    for materialised_s3_file in materialised_s3_files:
        materialised_s3_file.unlink(missing_ok=True)


# Caching here would be wrong. A batch with failed documents
# returns a `FeedResult` and finishes Completed, so it
# would cache as a success and never be re-fed.
@task(cache_policy=NO_CACHE)
@tracer.start_as_current_span("feed_batch")
def feed_batch(
    endpoint: str,
    application: str,
    connections: int,
    feed_timeout_seconds_per_file: int,
    s3_bucket: str,
    batched_s3_keys: tuple[str, ...],
    derive_data_from_source: Callable[[dict], dict] | None = None,
) -> FeedResult:
    # All files from s3 and derived are stored in the `TemporaryDirectory`
    # and deleted when `with` block exists via `TemporaryDirectory.__exit__`.
    with tempfile.TemporaryDirectory(prefix="vespa-feeder-") as materialise_dir:
        materialised_s3_files = materialise_s3_files(
            bucket=s3_bucket,
            batched_s3_keys=list(batched_s3_keys),
            materialise_dir=Path(materialise_dir),
        )

        materialised_derived_files = materialise_derived_files(
            materialised_s3_files=materialised_s3_files,
            derive_data_from_source=derive_data_from_source,
        )

        # Halves peak disk - a batch otherwise holds both sets at once.
        delete_materialised_s3_files(materialised_s3_files=materialised_s3_files)

        return feed_derived_files(
            materialised_derived_files=materialised_derived_files,
            endpoint=endpoint,
            application=application,
            connections=connections,
            feed_timeout_seconds_per_file=feed_timeout_seconds_per_file,
        )


@tracer.start_as_current_span("vespa_feeder")
def vespa_feeder(
    s3_bucket: str,
    s3_prefix: str,
    s3_export_prefix: str | None = None,
    derive_data_from_source: Callable[[dict], dict] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    connections: int = _DEFAULT_CONNECTIONS,
    feed_timeout_seconds_per_file: int = _DEFAULT_VESPA_FEED_TIMEOUT_SECONDS_PER_FILE,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
) -> None:
    run_logger = get_run_logger()
    # this ensures we terminate any `vespa feed` processes
    # spawned from `feed_derived_files`
    _terminate_vespa_feed_processes_on_sigterm_handler()

    if not 0 < sample_rate <= 1:
        raise ValueError(f"sample_rate must be in (0, 1], got {sample_rate}")

    endpoint = get_ssm_parameter(name="/search/vespa/endpoint")
    application = get_ssm_parameter(name="/search/vespa/application")
    # This is read by Vespa CLI
    # @see: https://docs.vespa.ai/en/security/guide.html#use-endpoints
    os.environ["VESPA_CLI_DATA_PLANE_TOKEN"] = get_ssm_parameter(
        name="/search/vespa/write_token"
    )

    s3_export_prefix_pinned = s3_export_prefix is not None

    if s3_prefix.endswith(".jsonl"):
        # @related: LABEL_RELATIONSHIPS_DO_NOT_EXIST
        s3_keys = [s3_prefix]
        s3_prefix_full = s3_prefix
    else:
        if s3_export_prefix is None:
            s3_export_prefix = get_latest_s3_export_prefix(
                bucket=s3_bucket, prefix=s3_prefix
            )
        s3_prefix_full = f"{s3_prefix}{s3_export_prefix}"
        s3_keys = list_s3_keys(bucket=s3_bucket, prefix=s3_prefix_full)

    if sample_rate < 1:
        # Every nth key from the sorted listing, rather than the first n. Both
        # are deterministic - so every A/B variant feeds the identical subset -
        # but a stride is positionally unbiased, which matters if whatever
        # produced the files varies along the ordering.
        s3_keys = s3_keys[:: round(1 / sample_rate)]

    # Log and trace before we get going
    run_logger.info(
        f"Feeding {len(s3_keys)} files from s3://{s3_bucket}/{s3_prefix_full} "
        f"in batches of {batch_size} (sample_rate={sample_rate})"
    )
    trace.get_current_span().set_attributes(
        {
            "s3_bucket": s3_bucket,
            "s3_prefix": s3_prefix,
            "s3_export_prefix": s3_export_prefix or "",
            "s3_export_prefix_pinned": s3_export_prefix_pinned,
            "batch_size": batch_size,
            "sample_rate": sample_rate,
            "connections": connections,
            "s3_keys_len": len(s3_keys),
        }
    )

    s3_key_batches = list(batched(s3_keys, batch_size))

    feed_results_futures: list[PrefectFuture[FeedResult]] = []
    for batch_number, batched_s3_keys in enumerate(s3_key_batches, start=1):
        run_logger.info(
            f"Feeding batch {batch_number}/{len(s3_key_batches)} "
            f"({len(batched_s3_keys)} files)"
        )
        feed_results_futures.append(
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

    # resolve feed_results_futures and raise on any exceptions
    feed_results: list[FeedResult] = []
    feed_results_exceptions: list[BaseException] = []

    # the finally is for a cancel mid-drain: `raise_on_failure=False` means no
    # batch raises here, so it is SIGTERM that would otherwise lose the summary.
    try:
        for feed_result_future in feed_results_futures:
            # we do not raise to be able to aggregate and report on this in the markdown artifact.
            feed_result = feed_result_future.result(raise_on_failure=False)
            if isinstance(feed_result, BaseException):
                run_logger.error(
                    f"Batch raised {type(feed_result).__name__}: {feed_result}"
                )
                feed_results_exceptions.append(feed_result)
                continue

            feed_results.append(feed_result)
    finally:
        # we then get the known failures from the vespa FeedResult
        feed_results_errors = [result for result in feed_results if result.errors]

        # publish the artifact in Prefect
        create_markdown_artifact(
            key="vespa-feeder-run-summary",
            markdown=_build_run_summary_markdown(
                feed_results, feed_results_errors, feed_results_exceptions
            ),
            description="Aggregate summary of the vespa-feeder run across all files",
        )

    if feed_results_errors or feed_results_exceptions:
        raise VespaFeederFailed(
            f"vespa_feed: of {len(feed_results) + len(feed_results_exceptions)} "
            f"batch(es), {len(feed_results_errors)} lost records and "
            f"{len(feed_results_exceptions)} raised. See the "
            "vespa-feeder-run-summary artifact and per-batch error logs above.",
            feed_results_errors,
            feed_results_exceptions,
        )
