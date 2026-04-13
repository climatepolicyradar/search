"""
Prefect flow: download a JSONL feed file from S3 then push it to Vespa.

Typical usage
-------------
Run a single index locally:

    uv run python -m vespa_feeder.flow

Run multiple indexes from another flow:

    from vespa_feeder.flow import vespa_feed_flow
    from vespa_feeder.config import FeedJob

    vespa_feed_flow(FeedJob(
        s3_bucket="my-bucket",
        s3_key="search/vespa/documents.jsonl.gz",
        vespa_url="https://my-app.vespa-cloud.com",
        vespa_write_token="...",
        index_name="documents",
    ))
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from prefect import flow, task

from vespa_feeder.config import FeedJob
from vespa_feeder.s3 import download, s3_uri
from vespa_feeder.vespa import feed


@task(log_prints=True)
def download_feed_file(job: FeedJob, dest: Path) -> Path:
    uri = s3_uri(job.s3_bucket, job.s3_key)
    print(f"Downloading {uri} …")
    path = download(job.s3_bucket, job.s3_key, dest)
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"Downloaded {uri} → {path} ({size_mb:.1f} MB)")
    return path


@task(log_prints=True)
def feed_to_vespa(job: FeedJob, feed_file: Path) -> None:
    print(f"Feeding {feed_file.name} → {job.vespa_url} (index: {job.index_name})")
    feed(
        feed_file=feed_file,
        vespa_url=job.vespa_url,
        write_token=job.vespa_write_token,
    )
    print(f"Feed complete for index: {job.index_name}")


@flow(log_prints=True)
def vespa_feed_flow(job: FeedJob) -> None:
    """Download a JSONL feed file from S3 and push it to Vespa."""
    filename = Path(job.s3_key).name
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / filename
        feed_file = download_feed_file(job, dest)
        feed_to_vespa(job, feed_file)


if __name__ == "__main__":
    # Quick local run — reads config from environment / .env
    vespa_feed_flow(FeedJob())  # type: ignore[call-arg]
