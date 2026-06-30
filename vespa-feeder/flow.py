import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import boto3
import orjson
from mypy_boto3_s3 import S3Client
from opentelemetry.trace import StatusCode
from prefect.artifacts import create_markdown_artifact
from prefect.runtime import deployment, flow_run
from slack_notify import SlackNotify
from telemetry import feeder_metrics, set_feed_stats, shutdown, tracer

from prefect import flow, get_run_logger, task

logger = logging.getLogger(__name__)


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
    http_error_count: int  # http.response.error.count
    failed_documents: list[FailedDocument]


VespaFeedError = VespaHTTPError | VespaResponseError

_GIVING_UP_RE = re.compile(r"^feed: (.+) for put (\S+): giving up", re.MULTILINE)


def _parse_failed_documents(stderr: str) -> list[FailedDocument]:
    return [
        FailedDocument(doc_id=giving_up_match.group(2), error=giving_up_match.group(1))
        for giving_up_match in _GIVING_UP_RE.finditer(stderr)
    ]


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
                run_logger.info(f"Downloaded s3://{bucket}/{key} → {local_path}")
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
def vespa_feed(feed_path: Path) -> None:
    run_logger = get_run_logger()

    endpoint = get_ssm_parameter(name="/search/vespa/endpoint")
    write_token = get_ssm_parameter(name="/search/vespa/write_token")
    application = get_ssm_parameter(name="/search/vespa/application")

    start_time = time.perf_counter()
    try:
        with tracer.start_as_current_span("vespa_feed") as span:
            span.set_attribute("vespa.endpoint", endpoint)
            span.set_attribute("vespa.application", application)
            span.set_attribute("feed.path", str(feed_path))

            input_record_count = sum(1 for line in feed_path.open() if line.strip())
            span.set_attribute("feed.input_record_count", input_record_count)

            run_logger.info(
                "Feeding %s to %s (application: %s, records: %d)",
                feed_path,
                endpoint,
                application,
                input_record_count,
            )

            result = subprocess.run(
                [
                    "vespa",
                    "feed",
                    str(feed_path),
                    "--target",
                    endpoint,
                    "--application",
                    application,
                ],
                env={**os.environ, "VESPA_CLI_DATA_PLANE_TOKEN": write_token},
                capture_output=True,
                text=True,
            )

            if result.stderr:
                run_logger.warning("vespa feed stderr: %s", result.stderr)
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

            response_str = orjson.dumps(
                response_data, option=orjson.OPT_INDENT_2
            ).decode()

            feeder_operation_count = response_data.get("feeder.operation.count", 0)
            feeder_ok_count = response_data.get("feeder.ok.count", 0)
            feeder_error_count = response_data.get("feeder.error.count", 0)
            http_response_error_count = response_data.get(
                "http.response.error.count", 0
            )
            http_response_code_counts = response_data.get(
                "http.response.code.counts", {}
            )
            too_many_requests_count = http_response_code_counts.get("429", 0)

            span.set_attribute("feed.operation_count", feeder_operation_count)
            span.set_attribute("feed.ok_count", feeder_ok_count)
            span.set_attribute("feed.feeder_error_count", feeder_error_count)
            span.set_attribute("feed.http_error_count", http_response_error_count)

            set_feed_stats(
                input_count=input_record_count,
                ok_count=feeder_ok_count,
                total_errors=feeder_error_count
                + (feeder_operation_count - feeder_ok_count),
            )

            run_logger.info(
                f"vespa feed stats: input={input_record_count} operation={feeder_operation_count} "
                f"ok={feeder_ok_count} feeder_errors={feeder_error_count} http_errors={http_response_error_count} "
                f"throttled={too_many_requests_count} codes={http_response_code_counts}"
            )

            # We warn on throttled requests, as they have generally self-healed, but they could be an indicator of a larger issue.
            if too_many_requests_count:
                run_logger.warning(
                    f"vespa_feed: {too_many_requests_count} requests throttled (429) but retried successfully"
                )

            feeder_metrics.record_feed_stats(
                ok_count=feeder_ok_count,
                total_errors=feeder_error_count
                + (feeder_operation_count - feeder_ok_count),
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )

            failed_documents = _parse_failed_documents(result.stderr)

            errors: list[VespaFeedError] = []

            # feeder.error.count is transport-layer failures (connection refused, TLS error,
            # etc.) where the CLI gave up before receiving any HTTP response.
            # We error as these documents would be considered missed.
            if feeder_error_count > 0:
                errors.append(
                    VespaHTTPError(
                        feeder_error_count=feeder_error_count,
                        failed_documents=failed_documents,
                    )
                )

            # ok.count < operation.count means records were submitted but not indexed -
            # the CLI got HTTP responses but exhausted retries without a 2xx.
            if feeder_ok_count < feeder_operation_count:
                errors.append(
                    VespaResponseError(
                        ok_count=feeder_ok_count,
                        operation_count=feeder_operation_count,
                        http_error_count=http_response_error_count,
                        failed_documents=failed_documents,
                    )
                )

            has_errors = len(errors) > 0
            has_warnings = too_many_requests_count > 0

            markdown = "### Vespa Feed Response\n\n"
            if has_errors:
                markdown += "🚨 **Error: records were not indexed.**\n\n"
            elif has_warnings:
                markdown += "⚠️ **Warning: requests were throttled but retried successfully.**\n\n"
            else:
                markdown += "✅ **Success: all records indexed.**\n\n"
            markdown += f"```json\n{response_str}\n```"

            create_markdown_artifact(
                key="vespa-feed-response",
                markdown=markdown,
                description="Vespa Feed Output Data",
            )

            if errors:
                span.set_status(StatusCode.ERROR, "Vespa feed response contains errors")
                for doc in failed_documents:
                    run_logger.error(
                        f"vespa_feed: failed document doc_id={doc.doc_id} error={doc.error}"
                    )
                raise ExceptionGroup("vespa_feed: failed", errors)
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
)
def vespa_feeder_flow(
    s3_bucket: str,
    s3_key: str,
) -> None:
    run_logger = get_run_logger()

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

            feed_paths = download_from_s3(bucket=s3_bucket, key=s3_key)
            for feed_path in feed_paths:
                vespa_feed(feed_path=feed_path)
    except Exception:
        _failed = True
        raise
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
