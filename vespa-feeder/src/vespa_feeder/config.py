"""
Configuration for the vespa-feeder service.

A FeedJob describes one S3 source → Vespa target pair.
Multiple jobs can be run in a single flow invocation, which is how
you scale across indexes (documents, passages, labels, etc.).

Environment variables (with VESPA_FEEDER_ prefix):
  VESPA_FEEDER_VESPA_URL          - Vespa endpoint, e.g. https://my-app.vespa-cloud.com
  VESPA_FEEDER_VESPA_WRITE_TOKEN  - Bearer token for write access (omit for local/no-auth)
  VESPA_FEEDER_S3_BUCKET          - S3 bucket containing the JSONL feed file
  VESPA_FEEDER_S3_KEY             - S3 key, e.g. search/vespa/documents.jsonl.gz
  VESPA_FEEDER_INDEX_NAME         - human label for logs / Prefect UI

For multi-index use, build FeedJob objects directly in your flow or
deployment script rather than relying on env-var defaults.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class FeedJob(BaseSettings):
    """All configuration required to feed one S3 file into one Vespa index."""

    model_config = SettingsConfigDict(env_prefix="VESPA_FEEDER_", env_file=".env")

    # S3 source
    s3_bucket: str
    s3_key: str

    # Vespa target
    vespa_url: str
    # Bearer token for Vespa Cloud write access.
    # Leave unset when pointing at a local / unauthenticated Vespa instance.
    vespa_write_token: str | None = None

    # Optional label used in logging and Prefect run names
    index_name: str = "default"
