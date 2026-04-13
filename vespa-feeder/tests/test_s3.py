"""Tests for S3 download helpers."""

import json
from pathlib import Path

import pytest
from moto import mock_aws

from vespa_feeder.s3 import download, s3_uri
from tests.conftest import BUCKET, KEY_PLAIN, KEY_GZ, SAMPLE_DOCS


def test_download_plain(s3_with_feed, tmp_path):
    dest = tmp_path / "docs.jsonl"
    result = download(BUCKET, KEY_PLAIN, dest, s3=s3_with_feed)

    assert result == dest
    assert dest.exists()
    lines = [json.loads(l) for l in dest.read_text().splitlines() if l.strip()]
    assert lines == SAMPLE_DOCS


def test_download_gz(s3_with_feed, tmp_path):
    dest = tmp_path / "docs.jsonl.gz"
    result = download(BUCKET, KEY_GZ, dest, s3=s3_with_feed)

    assert result == dest
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_download_creates_parent_dirs(s3_with_feed, tmp_path):
    dest = tmp_path / "deep" / "nested" / "docs.jsonl"
    download(BUCKET, KEY_PLAIN, dest, s3=s3_with_feed)
    assert dest.exists()


def test_s3_uri():
    assert s3_uri("my-bucket", "path/to/file.jsonl") == "s3://my-bucket/path/to/file.jsonl"
