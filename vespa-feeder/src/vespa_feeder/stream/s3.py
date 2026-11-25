import re
from collections.abc import Generator
from contextlib import closing
from typing import Any

import boto3
import orjson
from mypy_boto3_s3 import S3Client
from s3transfer.utils import S3_RETRYABLE_DOWNLOAD_ERRORS

from vespa_feeder.stream.stream import Source, Stream, run_logger

MAX_ATTEMPTS = 5


class S3Source(Source[dict[str, Any]]):
    def __init__(self, bucket: str, prefix: str) -> None:
        self._s3: S3Client = boto3.client("s3")
        self._paginator = self._s3.get_paginator("list_objects_v2")
        self._bucket = bucket
        self._prefix = prefix

    def _export_prefixes(self) -> Generator[str]:
        found_any_exports: bool = False
        for page in self._paginator.paginate(
            Bucket=self._bucket,
            Prefix=self._prefix,
            Delimiter="/",
        ):
            for s3_paths in page.get("CommonPrefixes", []):
                s3_path_prefix = s3_paths.get("Prefix", "")
                if re.fullmatch(r".*/\d{8}T\d{6}Z/", s3_path_prefix):
                    found_any_exports = True
                    yield s3_path_prefix

        if not found_any_exports:
            raise FileNotFoundError(
                f"No timestamped exports under s3://{self._bucket}/{self._prefix}"
            )

    def _bucket_keys(self, prefix: str) -> Generator[str]:
        found_any_keys: bool = False
        for page in self._paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for s3_object in page.get("Contents", []):
                if key := s3_object.get("Key"):
                    found_any_keys = True
                    yield key

        if not found_any_keys:
            raise FileNotFoundError(f"No objects found at s3://{self._bucket}/{prefix}")

    def _object_lines(self, key: str) -> Generator[dict[str, Any]]:
        with closing(self._s3.get_object(Bucket=self._bucket, Key=key)["Body"]) as body:
            for line in body.iter_lines(chunk_size=64 * 1024):
                if line.strip():
                    yield orjson.loads(line)

    def lines(self) -> Stream[dict[str, Any]]:
        """Yield every JSON line of the latest export."""
        for key in self._bucket_keys(max(self._export_prefixes())):
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    yield from self._object_lines(key)
                    break
                except S3_RETRYABLE_DOWNLOAD_ERRORS:
                    if attempt == MAX_ATTEMPTS:
                        raise
                    run_logger().warning(
                        f"Re-reading s3://{self._bucket}/{key} after a broken stream "
                        f"(attempt {attempt}/{MAX_ATTEMPTS})"
                    )
