import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import boto3
import orjson
from opentelemetry.trace import StatusCode
from prefect.artifacts import create_markdown_artifact
from prefect.runtime import deployment, flow_run
from slack_notify import SlackNotify
from telemetry import (
    record_feed_stats,
    record_run_duration,
    record_task_duration,
    set_feed_stats,
    setup_telemetry,
    shutdown,
)

from prefect import flow, get_run_logger, task

logger = logging.getLogger(__name__)


class VespaFeedError(Exception):
    pass


@task
def download_from_s3(bucket: str, key: str) -> Path:
    run_logger = get_run_logger()
    local_path = Path(tempfile.gettempdir()) / key.split("/")[-1]
    tracer = setup_telemetry()

    start_time = time.perf_counter()
    try:
        with tracer.start_as_current_span("download_from_s3") as span:
            span.set_attribute("s3.bucket", bucket)
            span.set_attribute("s3.key", key)
            run_logger.info("Downloading s3://%s/%s → %s", bucket, key, local_path)
            try:
                boto3.client("s3").download_file(bucket, key, str(local_path))
            except Exception as exc:
                run_logger.error(
                    "Failed to download s3://%s/%s: %s", bucket, key, exc, exc_info=True
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
        record_task_duration(
            "download_from_s3",
            time.perf_counter() - start_time,
            deployment.name or "local",
        )

    return local_path


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
    tracer = setup_telemetry()

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

            ok_count = response_data.get("feeder.ok.count", 0)
            error_count = response_data.get("feeder.error.count", 0)
            http_error_count = response_data.get("http.response.error.count", 0)
            exception_count = response_data.get("http.exception.count", 0)
            codes = response_data.get("http.response.code.counts", {})
            has_non_200 = any(code != "200" for code in codes)

            span.set_attribute("feed.ok_count", ok_count)
            span.set_attribute("feed.error_count", error_count)
            span.set_attribute("feed.http_error_count", http_error_count)
            span.set_attribute("feed.exception_count", exception_count)

            set_feed_stats(
                input_count=input_record_count,
                ok_count=ok_count,
                total_errors=error_count + http_error_count + exception_count,
            )

            run_logger.info(
                "vespa feed stats: input=%d ok=%d errors=%d http_errors=%d exceptions=%d codes=%s",
                input_record_count,
                ok_count,
                error_count,
                http_error_count,
                exception_count,
                codes,
            )

            record_feed_stats(
                ok_count=ok_count,
                total_errors=error_count + http_error_count + exception_count,
                deployment_name=deployment.name or "local",
            )

            has_error = (
                has_non_200
                or exception_count > 0
                or http_error_count > 0
                or error_count > 0
            )

            markdown = "### Vespa Feed Response\n\n"
            if has_error:
                markdown += "🚨 **WARNING: ERROR DETECTED IN FEED RESPONSE!** 🚨\n\n"
            markdown += f"```json\n{response_str}\n```"

            create_markdown_artifact(
                key="vespa-feed-response",
                markdown=markdown,
                description="Vespa Feed Output Data",
            )

            if has_error:
                span.set_status(StatusCode.ERROR, "Vespa feed response contains errors")
                run_logger.error(
                    "Vespa feed issue detected: ok=%d errors=%d http_errors=%d exceptions=%d "
                    "feed_path=%s response=%s",
                    ok_count,
                    error_count,
                    http_error_count,
                    exception_count,
                    feed_path,
                    response_str,
                )
                raise VespaFeedError(
                    f"Urgent: vespa feed issue detected in response:\n{response_str}"
                )
    finally:
        record_task_duration(
            "vespa_feed", time.perf_counter() - start_time, deployment.name or "local"
        )


@flow(
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
)
def vespa_feeder_flow(
    s3_bucket: str = "cpr-cache",
    s3_key: str = "search/vespa/labels_feed_materializer.jsonl",
) -> None:
    tracer = setup_telemetry()
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
    try:
        with tracer.start_as_current_span("vespa_feeder_flow") as span:
            span.set_attribute("prefect.deployment_name", deployment_name)
            span.set_attribute("prefect.flow_run_id", flow_run_id)
            span.set_attribute("prefect.flow_run_name", flow_run_name)
            span.set_attribute("flow.s3_bucket", s3_bucket)
            span.set_attribute("flow.s3_key", s3_key)

            feed_path = download_from_s3(bucket=s3_bucket, key=s3_key)
            vespa_feed(feed_path=feed_path)
    finally:
        record_run_duration(time.perf_counter() - start_time, deployment_name)
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
    vespa_feeder_flow()
