import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
import orjson
from mypy_boto3_s3 import S3Client
from opentelemetry.trace import StatusCode
from prefect.artifacts import create_markdown_artifact
from prefect.client.schemas.objects import State
from prefect.runtime import deployment, flow_run
from prefect.states import Failed
from pydantic import BaseModel, ConfigDict, Field
from slack_notify import SlackNotify
from telemetry import feeder_metrics, set_feed_stats, shutdown, tracer

from prefect import flow, get_run_logger, task

logger = logging.getLogger(__name__)

# Vespa's own guidance warns against many worker processes each opening their
# own full connection pool (default 8 connections per `vespa feed` process) -
# that's a TLS-handshake storm with no shared backpressure state. We cap how
# many `vespa feed` subprocesses run at once and pin each to a single
# connection so overall concurrency stays in a sane, tunable range.
# 8-way concurrency OOMKilled the passages feed (200k-record files) even at
# 1024 CPU / 2048MB, so this is capped lower for that container size.
_MAX_CONCURRENT_FEEDS = 4
_feed_semaphore = threading.Semaphore(_MAX_CONCURRENT_FEEDS)

# On SIGTERM (e.g. a graceful ECS stop or Prefect cancellation) we terminate
# any `vespa feed` subprocesses still running rather than leaving them as
# orphans the flow run can no longer track. Each `vespa feed` invocation is
# idempotent per-document, so killing one mid-feed just means its file gets
# fully retried on the next run.
_live_processes: set[subprocess.Popen] = set()
_live_processes_lock = threading.Lock()


def _terminate_live_processes(signum, _) -> None:
    with _live_processes_lock:
        processes = list(_live_processes)
    logger.warning(
        "Received signal %d, terminating %d in-flight vespa feed process(es)",
        signum,
        len(processes),
    )
    for process in processes:
        process.terminate()


def _register_sigterm_handler() -> None:
    # Prefect's runner can re-import this module from a worker thread (e.g. to
    # resolve on_crashed hooks after the flow run's own process has already
    # died), and signal.signal() raises ValueError outside the main thread. It
    # only needs to be registered once, in the process actually running the
    # flow, so we call this from vespa_feeder_flow rather than at import time.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _terminate_live_processes)


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
    http_response_error_count: int = Field(alias="http.response.error.count", default=0)
    http_response_code_counts: dict[str, int] = Field(
        alias="http.response.code.counts", default_factory=dict
    )


@dataclass
class FeedResult:
    feed_path: Path
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
            sample = "; ".join(f"`{doc.doc_id}`: {doc.error}" for doc in failed_docs[:3])
            if len(failed_docs) > 3:
                sample += f" (+{len(failed_docs) - 3} more)"
            markdown += (
                f"| `{r.feed_path.name}` | {r.ok_count}/{r.operation_count} | "
                f"{r.operation_count - r.ok_count} | {sample or '—'} |\n"
            )

    return markdown


@task
def download_from_s3(bucket: str, key: str) -> list[Path]:
    # Keys ending in .jsonl are single files; anything else is treated as a folder prefix.
    # All pipelines are being migrated to the folder pattern, so this check is temporary.
    run_logger = get_run_logger()
    s3: S3Client = boto3.client("s3")

    start_time = time.perf_counter()
    paths: list[Path] = []

    try:
        with tracer.start_as_current_span("download_from_s3") as span:
            span.set_attribute("s3.bucket", bucket)
            span.set_attribute("s3.key", key)

            # This will become redundant, so this relatively basic conditional is OK
            # TODO: https://linear.app/climate-policy-radar/issue/APP-2236/feed-labels-from-snowflake-generated-json
            # TODO: https://linear.app/climate-policy-radar/issue/APP-2237/feed-passages-from-snowflake-generated-json
            if key.endswith(".jsonl"):
                local_path = Path(tempfile.gettempdir()) / key.split("/")[-1]
                run_logger.info(f"Downloading s3://{bucket}/{key} → {local_path}")
                try:
                    s3.download_file(bucket, key, str(local_path))
                except Exception as exc:
                    run_logger.error(
                        f"Failed to download s3://{bucket}/{key}: {exc}", exc_info=True
                    )
                    raise
                size_bytes = local_path.stat().st_size
                span.set_attribute("s3.downloaded_bytes", size_bytes)
                run_logger.info(
                    "Downloaded s3://%s/%s (%d bytes) → %s",
                    bucket,
                    key,
                    size_bytes,
                    local_path,
                )
                paths = [local_path]
            else:
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

                run_logger.info(
                    f"Found {len(objects)} objects at s3://{bucket}/{prefix}"
                )
                span.set_attribute("s3.object_count", len(objects))

                for obj in objects:
                    obj_key = obj.get("Key", "")
                    obj_path = Path(tempfile.gettempdir()) / obj_key.split("/")[-1]
                    run_logger.info(f"Downloading s3://{bucket}/{obj_key} → {obj_path}")
                    try:
                        s3.download_file(bucket, obj_key, str(obj_path))
                    except Exception as exc:
                        run_logger.error(
                            f"Failed to download s3://{bucket}/{obj_key}: {exc}",
                            exc_info=True,
                        )
                        raise
                    paths.append(obj_path)

                run_logger.info(
                    f"Downloaded {len(paths)} objects from s3://{bucket}/{prefix}"
                )
    finally:
        feeder_metrics.record_task_duration(
            "download_from_s3",
            time.perf_counter() - start_time,
            deployment.name or "local",
        )

    return paths


@task
def get_ssm_parameter(name: str) -> str:
    response = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
    value = response["Parameter"].get("Value")
    if value is None:
        raise ValueError(f"SSM parameter {name} has no value")
    return value.strip()


@task
def vespa_feed(feed_path: Path, endpoint: str, application: str) -> FeedResult:
    run_logger = get_run_logger()

    start_time = time.perf_counter()
    try:
        with tracer.start_as_current_span("vespa_feed") as span:
            span.set_attribute("vespa.endpoint", endpoint)
            span.set_attribute("vespa.application", application)
            span.set_attribute("feed.path", str(feed_path))

            input_record_count = sum(1 for line in feed_path.open() if line.strip())
            span.set_attribute("feed.input_record_count", input_record_count)

            with _feed_semaphore:
                run_logger.info(
                    "Feeding %s to %s (application: %s, records: %d)",
                    feed_path,
                    endpoint,
                    application,
                    input_record_count,
                )

                process = subprocess.Popen(
                    [
                        "vespa",
                        "feed",
                        str(feed_path),
                        "--target",
                        endpoint,
                        "--application",
                        application,
                        "--connections",
                        "1",
                        "--verbose",
                    ],
                    # VESPA_CLI_DATA_PLANE_TOKEN is set on this process's own
                    # environment by vespa_feeder_flow, not passed as a task
                    # parameter - Prefect displays task parameters in the UI,
                    # and this value is a secret.
                    env=os.environ,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                with _live_processes_lock:
                    _live_processes.add(process)
                try:
                    stdout, stderr = process.communicate()
                finally:
                    with _live_processes_lock:
                        _live_processes.discard(process)

                result = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
                )

            if result.stderr:
                span.set_attribute("feed.stderr", result.stderr[:4096])

            if result.returncode != 0:
                run_logger.error(
                    "vespa feed exited with code %d: feed_path=%s stderr=%s",
                    result.returncode,
                    feed_path,
                    result.stderr,
                )
                result.check_returncode()

            try:
                response_data = orjson.loads(result.stdout)
            except orjson.JSONDecodeError:
                run_logger.error(
                    "Failed to parse vespa feed response as JSON. Raw output:\n%s",
                    result.stdout,
                )
                raise

            feed_response = VespaFeedResponse.model_validate(response_data)

            # http_response_error_count from the CLI counts ALL non-2xx responses,
            # which already includes 429s - it is not a distinct quantity on top
            # of throttled_count. We split it here into two counters that are
            # genuinely additive: throttled_count (429s) and other_http_error_count
            # (everything else non-2xx, e.g. 5xx), so summing fields never double
            # counts the same requests.
            throttled_count = feed_response.http_response_code_counts.get("429", 0)
            other_http_error_count = (
                feed_response.http_response_error_count - throttled_count
            )
            missing_count = (
                feed_response.feeder_operation_count - feed_response.feeder_ok_count
            )

            span.set_attribute(
                "feed.feeder_operation_count", feed_response.feeder_operation_count
            )
            span.set_attribute("feed.feeder_ok_count", feed_response.feeder_ok_count)
            span.set_attribute("feed.missing_count", missing_count)
            span.set_attribute(
                "feed.feeder_error_count", feed_response.feeder_error_count
            )
            span.set_attribute("feed.throttled_count", throttled_count)
            span.set_attribute("feed.other_http_error_count", other_http_error_count)

            set_feed_stats(
                input_count=input_record_count,
                ok_count=feed_response.feeder_ok_count,
                total_errors=missing_count,
            )

            # feeder_errors, throttled and other_http_errors are retry *attempts* -
            # most succeed once the CLI retries them, so they don't by themselves
            # mean any record was lost. missing (operation - ok) is the only
            # number that reflects a real, permanent outcome. The three retry
            # counters are disjoint (transport failure vs. 429 vs. other non-2xx),
            # so they can be safely summed without double counting.
            run_logger.info(
                f"vespa feed stats: feed_path={feed_path} input={input_record_count} "
                f"operation={feed_response.feeder_operation_count} ok={feed_response.feeder_ok_count} "
                f"missing={missing_count} feeder_errors={feed_response.feeder_error_count} "
                f"throttled={throttled_count} other_http_errors={other_http_error_count} "
                f"codes={feed_response.http_response_code_counts}"
            )

            retry_attempt_count = (
                feed_response.feeder_error_count + throttled_count + other_http_error_count
            )

            if missing_count > 0:
                run_logger.error(
                    f"vespa_feed OUTCOME: feed_path={feed_path} "
                    f"{feed_response.feeder_ok_count}/{feed_response.feeder_operation_count} records fed successfully "
                    f"- {missing_count} MISSING (not recovered after retries)"
                )
            else:
                run_logger.info(
                    f"vespa_feed OUTCOME: feed_path={feed_path} "
                    f"all {feed_response.feeder_ok_count}/{feed_response.feeder_operation_count} records fed successfully"
                )

            if retry_attempt_count > 0:
                run_logger.info(
                    f"vespa_feed OUTCOME: feed_path={feed_path} "
                    f"{retry_attempt_count} requests needed a retry (mostly throttling, HTTP 429) "
                    "- this counts retry events, not records, and does not by itself mean any "
                    "record was lost; see the MISSING count above for the only figure that does"
                )

            feeder_metrics.record_feed_stats(
                input_count=input_record_count,
                ok_count=feed_response.feeder_ok_count,
                total_errors=missing_count,
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )

            failed_documents = _parse_failed_documents(result.stderr)

            errors: list[VespaFeedError] = []

            # missing_count (ok < operation) is the only signal that means records
            # were actually lost, so it's the only thing that fails the file.
            # feeder_error_count and http response errors are retry attempts that
            # mostly self-heal (see the OUTCOME log lines above) - a file with
            # feeder_error_count > 0 but missing_count == 0 had every one of those
            # attempts eventually succeed, so it must not be marked as failed.
            if missing_count > 0:
                if feed_response.feeder_error_count > 0:
                    errors.append(
                        VespaHTTPError(
                            feeder_error_count=feed_response.feeder_error_count,
                            failed_documents=failed_documents,
                        )
                    )
                errors.append(
                    VespaResponseError(
                        ok_count=feed_response.feeder_ok_count,
                        operation_count=feed_response.feeder_operation_count,
                        throttled_count=throttled_count,
                        other_http_error_count=other_http_error_count,
                        failed_documents=failed_documents,
                    )
                )

            if errors:
                span.set_status(StatusCode.ERROR, "Vespa feed response contains errors")
                for doc in failed_documents:
                    run_logger.error(
                        f"vespa_feed: failed document feed_path={feed_path} "
                        f"doc_id={doc.doc_id} error={doc.error}"
                    )

            return FeedResult(
                feed_path=feed_path,
                input_count=input_record_count,
                operation_count=feed_response.feeder_operation_count,
                ok_count=feed_response.feeder_ok_count,
                feeder_error_count=feed_response.feeder_error_count,
                throttled_count=throttled_count,
                other_http_error_count=other_http_error_count,
                errors=errors,
            )
    finally:
        feeder_metrics.record_task_duration(
            "vespa_feed",
            time.perf_counter() - start_time,
            deployment.name or "local",
        )


@flow(
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def vespa_feeder_flow(
    s3_bucket: str,
    s3_key: str,
) -> State | None:
    run_logger = get_run_logger()
    _register_sigterm_handler()

    deployment_name = deployment.name or "local"
    flow_run_id = flow_run.id or "unknown"
    flow_run_name = flow_run.name or "unknown"

    run_logger.info(
        "vespa_feeder_flow started: deployment=%s flow_run_id=%s flow_run_name=%s "
        "s3_bucket=%s s3_key=%s",
        deployment_name,
        flow_run_id,
        flow_run_name,
        s3_bucket,
        s3_key,
    )

    start_time = time.perf_counter()
    _failed = False
    try:
        with tracer.start_as_current_span("vespa_feeder_flow") as span:
            span.set_attribute("prefect.deployment_name", deployment_name)
            span.set_attribute("prefect.flow_run_id", flow_run_id)
            span.set_attribute("prefect.flow_run_name", flow_run_name)
            span.set_attribute("flow.s3_bucket", s3_bucket)
            span.set_attribute("flow.s3_key", s3_key)

            endpoint = get_ssm_parameter(name="/search/vespa/endpoint")
            application = get_ssm_parameter(name="/search/vespa/application")
            # Set once on this process's environment rather than passed as a
            # task parameter to vespa_feed - Prefect displays task parameters
            # in the UI/API, and this value is a secret.
            os.environ["VESPA_CLI_DATA_PLANE_TOKEN"] = get_ssm_parameter(
                name="/search/vespa/write_token"
            )

            feed_paths = download_from_s3(bucket=s3_bucket, key=s3_key)
            futures = [
                vespa_feed.submit(
                    feed_path=feed_path,
                    endpoint=endpoint,
                    application=application,
                )
                for feed_path in feed_paths
            ]
            results = [future.result() for future in futures]

            total_input = sum(result.input_count for result in results)
            total_operation = sum(result.operation_count for result in results)
            total_ok = sum(result.ok_count for result in results)
            total_missing = total_operation - total_ok
            total_feeder_errors = sum(result.feeder_error_count for result in results)
            total_throttled = sum(result.throttled_count for result in results)
            total_other_http_errors = sum(
                result.other_http_error_count for result in results
            )
            failed_results = [result for result in results if result.errors]

            span.set_attribute("feed.total_input_count", total_input)
            span.set_attribute("feed.total_ok_count", total_ok)
            span.set_attribute("feed.total_missing_count", total_missing)
            span.set_attribute("feed.failed_file_count", len(failed_results))

            # Overwrite the per-file stats set by the last vespa_feed call so the
            # Slack notification reflects the whole run, not just the last file.
            set_feed_stats(
                input_count=total_input,
                ok_count=total_ok,
                total_errors=total_missing,
            )

            run_logger.info(
                f"vespa_feeder_flow aggregate stats: files={len(results)} "
                f"input={total_input} operation={total_operation} ok={total_ok} "
                f"missing={total_missing} feeder_errors={total_feeder_errors} "
                f"throttled={total_throttled} other_http_errors={total_other_http_errors} "
                f"failed_files={len(failed_results)}"
            )

            create_markdown_artifact(
                key="vespa-feeder-run-summary",
                markdown=_build_run_summary_markdown(results, failed_results),
                description="Aggregate summary of the vespa-feeder run across all files",
            )

            if failed_results:
                for r in failed_results:
                    run_logger.error(
                        f"vespa_feeder_flow: feed_path={r.feed_path} failed "
                        f"(ok={r.ok_count}/{r.operation_count}, "
                        f"missing={r.operation_count - r.ok_count})"
                    )
                failed_paths = ", ".join(str(r.feed_path) for r in failed_results)
                _failed = True
                return Failed(
                    message=(
                        f"vespa_feed: failed for {len(failed_results)}/{len(results)} "
                        f"file(s): {failed_paths}. See the vespa-feeder-run-summary "
                        "artifact and per-file error logs above for details."
                    )
                )
    except Exception as exc:
        _failed = True
        run_logger.error(
            "vespa_feeder_flow failed with an unexpected error", exc_info=True
        )
        return Failed(message=str(exc))
    finally:
        feeder_metrics.record_run_duration(
            time.perf_counter() - start_time, deployment_name
        )
        if _failed:
            feeder_metrics.record_run_failed(deployment_name, flow_run_name)
        else:
            feeder_metrics.record_run_completed(deployment_name, flow_run_name)
        shutdown()

    run_logger.info(
        "vespa_feeder_flow completed: deployment=%s flow_run_id=%s flow_run_name=%s "
        "s3_bucket=%s s3_key=%s",
        deployment_name,
        flow_run_id,
        flow_run_name,
        s3_bucket,
        s3_key,
    )


if __name__ == "__main__":
    vespa_feeder_flow(
        s3_bucket="cpr-cache", s3_key="search/vespa/labels_feed_materializer.jsonl"
    )
