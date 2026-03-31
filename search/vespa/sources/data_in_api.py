from collections.abc import Iterator
from pathlib import Path
from typing import Required, TypedDict

import boto3
import orjson

from search.config import REPO_ROOT_DIR

DATA_CACHE_FILE = (
    REPO_ROOT_DIR
    / ".data_cache"
    / "vespa"
    / "sources"
    / "data_in_api"
    / "documents-latest.jsonl"
)


class SourceLabel(TypedDict):
    id: str
    type: str
    value: str


class SourceLabelRelationship(TypedDict):
    type: str
    value: SourceLabel
    timestamp: str | None


class SourceDocument(TypedDict, total=False):
    id: Required[str]
    title: Required[str]
    description: str | None
    labels: list[SourceLabelRelationship]
    attributes: dict[str, str | float | int | bool]


def extract() -> Path:
    DATA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_CACHE_FILE.exists():
        print(f"{DATA_CACHE_FILE} cache missing. Downloading file {DATA_CACHE_FILE}...")
        s3 = boto3.client("s3")
        s3.download_file(
            "cpr-cache",
            "pipelines/data-in-pipeline/navigator_family/documents-latest.jsonl",
            str(DATA_CACHE_FILE),
        )
        print(f"Downloaded {DATA_CACHE_FILE} from S3.")
    else:
        print(f"{DATA_CACHE_FILE} already exists. Using cached file.")

    return DATA_CACHE_FILE


def read() -> Iterator[SourceDocument]:
    file = extract()
    with file.open("rb") as f:
        for line in f:
            yield orjson.loads(line)
