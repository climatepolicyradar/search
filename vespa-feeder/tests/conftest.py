import os
import tempfile
from pathlib import Path
from unittest.mock import create_autospec

import boto3
import pytest
import vespa_feeder as feeder
from feeder_metrics import FeederMetrics
from moto import mock_aws


def pytest_configure() -> None:
    # Before any test module imports telemetry, which otherwise builds real
    # OTLP exporters and retries against localhost:4318 for the whole session.
    os.environ.setdefault("DISABLE_OTEL_LOGGING", "true")


@pytest.fixture
def mock_aws_creds(monkeypatch):
    """Mocked AWS Credentials, so moto never reaches for real ones."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")  # nosec B105
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")  # nosec B105
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "test")  # nosec B105
    monkeypatch.setenv("AWS_SESSION_TOKEN", "test")  # nosec B105
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")


@pytest.fixture
def s3_client(mock_aws_creds):  # noqa: ARG001 - requested for its side effect
    """A moto-backed S3 client, which the feeder's own `boto3.client` also gets."""
    with mock_aws():
        yield boto3.client("s3", region_name="eu-west-1")


@pytest.fixture
def s3_bucket(s3_client):
    """An empty bucket for a test to populate; returns its name."""
    s3_client.create_bucket(
        Bucket="bucket",
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )
    return "bucket"


@pytest.fixture
def recording_metrics(monkeypatch):
    """A FeederMetrics stand-in that enforces the real method signatures."""
    metrics = create_autospec(FeederMetrics, instance=True)
    monkeypatch.setattr(feeder, "feeder_metrics", metrics)
    return metrics


@pytest.fixture
def temp_workspace(monkeypatch, tmp_path: Path) -> Path:
    """Point the feeder's `tempfile.gettempdir()` at a per-test directory."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path
