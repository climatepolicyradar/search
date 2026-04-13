"""
S3 helpers for the vespa-feeder.

Downloads an S3 object to a local path so the `vespa feed` CLI can read it.
Gzip-compressed files are kept compressed — the vespa CLI handles them natively.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _s3_client() -> "S3Client":
    return boto3.client("s3")


def download(bucket: str, key: str, dest: Path, s3: "S3Client | None" = None) -> Path:
    """
    Download an S3 object to *dest* and return the path.

    The caller is responsible for cleanup (e.g. via tempfile.TemporaryDirectory).
    """
    client = s3 or _s3_client()
    dest.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, key, str(dest))
    return dest


def s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"
