import time
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import boto3
import orjson
import polars as pl

from prefect import flow

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[1]

DATA_CACHE_DIR = (
    REPO_ROOT_DIR / ".data_cache" / "materialize_vespa_updates/from_data_in_api"
)
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_CACHE_FILE = DATA_CACHE_DIR / "documents-latest.parquet"
OUTPUT_FILE = DATA_CACHE_DIR / "documents-updates.jsonl"

DATA_IN_DOCUMENTS_SCHEMA = pl.Schema(
    {
        "labels": pl.List(
            pl.Struct(
                {
                    "timestamp": pl.String,
                    "type": pl.String,
                    "value": pl.Struct(
                        {
                            "id": pl.String,
                            "type": pl.String,
                            "value": pl.String,
                        }
                    ),
                }
            )
        ),
        "id": pl.String,
        "title": pl.String,
        "description": pl.String,
    }
)


class SourceLabel(TypedDict):
    id: str
    type: str
    value: str


class SourceLabelRelationship(TypedDict):
    type: str
    label: SourceLabel
    timestamp: str | None


class SourceDocument(TypedDict):
    id: str
    title: str
    description: str
    labels: list[SourceLabelRelationship]


def _extract_data() -> pl.DataFrame:
    if not API_CACHE_FILE.exists():
        s3 = boto3.client("s3")
        s3.download_file(
            "cpr-cache",
            "pipelines/data-in-pipeline/navigator_family/documents-latest.parquet",
            str(API_CACHE_FILE),
        )
    else:
        print(f"{API_CACHE_FILE} already exists. Skipping download.")

    return pl.read_parquet(
        API_CACHE_FILE, columns=["id", "title", "description", "labels"]
    )


def _to_api_document(document: dict) -> SourceDocument:
    """Reshape a parquet row into the API document format for the source field."""
    return {
        "id": document["id"],
        "title": document.get("title", "MISSING"),
        "description": document.get("description", "MISSING"),
        "labels": [
            {
                "type": label.get("type", "related"),
                "label": {
                    "id": label["value"]["id"],
                    "type": label["value"]["type"],
                    "value": label["value"]["value"],
                },
                "timestamp": label.get("timestamp"),
            }
            for label in (document.get("labels") or [])
        ],
    }


def _to_unix_timestamp(ts_str):
    """Safely convert ISO string to int, returns None if invalid/missing."""
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str).timestamp())
    except (ValueError, TypeError):
        return None


@flow(log_prints=True)
def materialize_vespa_updates_from_data_in_api():
    print("Extracting data-in-api...")
    start = time.time()
    data = _extract_data()
    print(
        f"Extracted {len(data)} documents from data-in-api ({time.time() - start:.2f}s)."
    )

    total = len(data)

    print(f"Writing {total} update_ops to {OUTPUT_FILE}...")
    start = time.time()
    with OUTPUT_FILE.open("wb") as f:
        for i, document in enumerate(data.iter_rows(named=True)):
            update_op = {
                "update": f"id:documents:documents::{document.get('id')}",
                "fields": {
                    "title": {"assign": document.get("title")},
                    "description": {"assign": document.get("description")},
                    "labels": {
                        "assign": [
                            {
                                "id": label["value"]["id"],
                                "type": label["value"]["type"],
                                "value": label["value"]["value"],
                                "timestamp": _to_unix_timestamp(label.get("timestamp")),
                                "relationship": label.get("type", "related"),
                            }
                            for label in (document.get("labels") or [])
                        ]
                    },
                    "document_source": {
                        "assign": orjson.dumps(_to_api_document(document)).decode()
                    },
                },
            }
            f.write(orjson.dumps(update_op) + b"\n")

            if i % 1000 == 0:
                print(f"Wrote {i}/{total} update_ops to {OUTPUT_FILE}.")

    print(f"Wrote {total} update_ops to {OUTPUT_FILE} ({time.time() - start:.2f}s).")

    print("Uploading to S3...")
    s3_client = boto3.client("s3")
    s3_client.upload_file(
        str(OUTPUT_FILE),
        "cpr-cache",
        "search/materialize_vespa_updates/from_data_in_api.jsonl",
    )
    print("Uploaded to S3.")


if __name__ == "__main__":
    materialize_vespa_updates_from_data_in_api()
