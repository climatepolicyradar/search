import json
import gzip
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


BUCKET = "test-bucket"
KEY_PLAIN = "feed/docs.jsonl"
KEY_GZ = "feed/docs.jsonl.gz"

SAMPLE_DOCS = [
    {
        "update": "id:documents:documents::doc-1",
        "create": True,
        "fields": {"title": {"assign": "Climate Policy"}, "year": {"assign": 2023}},
    },
    {
        "update": "id:documents:documents::doc-2",
        "create": True,
        "fields": {"title": {"assign": "Paris Agreement"}, "year": {"assign": 2015}},
    },
]


@pytest.fixture
def sample_jsonl_bytes() -> bytes:
    return b"\n".join(json.dumps(d).encode() for d in SAMPLE_DOCS)


@pytest.fixture
def sample_jsonl_gz_bytes(sample_jsonl_bytes) -> bytes:
    return gzip.compress(sample_jsonl_bytes)


@pytest.fixture
def s3_with_feed(sample_jsonl_bytes, sample_jsonl_gz_bytes):
    """Mocked S3 bucket pre-loaded with plain and gzipped JSONL feed files."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="eu-west-1")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        s3.put_object(Bucket=BUCKET, Key=KEY_PLAIN, Body=sample_jsonl_bytes)
        s3.put_object(Bucket=BUCKET, Key=KEY_GZ, Body=sample_jsonl_gz_bytes)
        yield s3


@pytest.fixture
def feed_job_local(tmp_path):
    """FeedJob pointing at a local (unauthenticated) Vespa instance."""
    from vespa_feeder.config import FeedJob

    return FeedJob(
        s3_bucket=BUCKET,
        s3_key=KEY_PLAIN,
        vespa_url="http://localhost:8080",
        index_name="test-documents",
    )


@pytest.fixture
def feed_job_cloud():
    """FeedJob pointing at a (mocked) Vespa Cloud instance with a write token."""
    from vespa_feeder.config import FeedJob

    return FeedJob(
        s3_bucket=BUCKET,
        s3_key=KEY_GZ,
        vespa_url="https://my-app.vespa-cloud.com",
        vespa_write_token="test-token-abc",
        index_name="test-documents-cloud",
    )
