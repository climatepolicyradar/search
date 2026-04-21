import subprocess
import tempfile
from pathlib import Path

import boto3
import orjson
from prefect.artifacts import create_markdown_artifact

from prefect import flow, get_run_logger, task


class VespaFeedError(Exception):
    pass


@task
def download_from_s3(bucket: str, key: str) -> Path:
    logger = get_run_logger()
    local_path = Path(tempfile.gettempdir()) / key.split("/")[-1]
    logger.info(f"Downloading s3://{bucket}/{key} → {local_path}")
    boto3.client("s3").download_file(bucket, key, str(local_path))
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
    logger = get_run_logger()
    endpoint = get_ssm_parameter(name="/search/vespa/endpoint")
    write_token = get_ssm_parameter(name="/search/vespa/write_token")
    application = get_ssm_parameter(name="/search/vespa/application")

    logger.info(f"Feeding {feed_path} to {endpoint}")
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
        env={**__import__("os").environ, "VESPA_CLI_DATA_PLANE_TOKEN": write_token},
        capture_output=True,
        text=True,
    )

    if result.stderr:
        logger.error(result.stderr)

    result.check_returncode()

    try:
        response_data = orjson.loads(result.stdout)
        response_str = orjson.dumps(response_data, option=orjson.OPT_INDENT_2).decode()
        logger.info(response_str)

        codes = response_data.get("http.response.code.counts", {})
        has_non_200 = any(code != "200" for code in codes)
        has_exceptions = response_data.get("http.exception.count", 0) > 0
        has_errors = response_data.get("http.response.error.count", 0) > 0
        has_feeder_errors = response_data.get("feeder.error.count", 0) > 0

        has_error = has_non_200 or has_exceptions or has_errors or has_feeder_errors

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
            raise VespaFeedError(
                f"Urgent: vespa feed issue detected in response:\n{response_str}"
            )

    except orjson.JSONDecodeError:
        logger.error(
            f"Failed to parse vespa feed response as JSON. Raw output:\n{result.stdout}"
        )
        raise


@flow(log_prints=True)
def vespa_feeder_flow(
    s3_bucket: str = "cpr-cache",
    s3_key: str = "search/vespa/labels_feed_materializer.jsonl",
) -> None:
    feed_path = download_from_s3(bucket=s3_bucket, key=s3_key)
    vespa_feed(feed_path=feed_path)


if __name__ == "__main__":
    vespa_feeder_flow()
