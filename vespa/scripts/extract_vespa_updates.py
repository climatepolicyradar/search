"""
Temporary script that extracts the data from the data-in-api and HuggingFace datasets.

It then caches it in the .data_cache directory so that it can be used to load data into Vespa.

When we get access to the data from the data lake - we can then use that as the data source.

Because of this - the robustness of this code is not a priority.
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import boto3
import orjson
import polars as pl
from dotenv import load_dotenv
from huggingface_hub import snapshot_download

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_CACHE_DIR = REPO_ROOT_DIR / ".data_cache"
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_CACHE_FILE = DATA_CACHE_DIR / "data-in-api" / "documents-latest.parquet"
API_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

PARQUET_DIR = (
    DATA_CACHE_DIR
    / "huggingface"
    / "climatepolicyradar"
    / "all-document-text-data-weekly"
)

name = "extract_vespa_updates"
PASSAGES_CACHE_FILE = DATA_CACHE_DIR / name / "passages_cache.parquet"
PASSAGES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_CACHE_DIR / name / "updates.jsonl"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

load_dotenv()


# region Types
# We use TypedDict over Pydantic as Pydantic significantly reduces the performance due to the scale of the data we load``
class TextBlock(TypedDict):
    type: str
    index: int
    text: str


class SourceLabel(TypedDict):
    id: str
    type: str
    title: str


class SourceLabelRelationship(TypedDict):
    type: str
    label: SourceLabel
    timestamp: str | None


class SourceDocument(TypedDict):
    id: str
    title: str
    description: str
    labels: list[SourceLabelRelationship]


class VespaLabel(TypedDict):
    id: int
    type: str
    value: str
    timestamp: int | None
    relationship: str


class VespaPassage(TypedDict):
    text_block_id: str
    language: str | None
    type: str
    type_confidence: float
    # This is not useful just as yet and add complexity due to its nested nature
    # coords: list[list[float]] | None
    page_number: int | None
    text: list[str]
    # you cannot have a field called index in vespa and it might not be useful
    # index: int


class VespaFields(TypedDict):
    title: str | None
    description: str | None
    labels: list[VespaLabel]
    passages: list[VespaPassage]
    source: str


class VespaUpdateOp(TypedDict):
    put: str
    fields: VespaFields


class HuggingFaceTextBlock(TypedDict):
    text_block_id: str
    language: str | None
    type: str
    type_confidence: float
    coords: list[list[float]] | None
    page_number: int | None
    text: list[str]
    index: int


API_DOCUMENTS_SCHEMA = pl.Schema(
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

# endregion


# region Extract
def extract_huggingface_data():
    if not PARQUET_DIR.exists():
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id="climatepolicyradar/all-document-text-data-weekly",
            repo_type="dataset",
            local_dir=PARQUET_DIR,
            token=os.getenv("HUGGINGFACE_TOKEN"),
        )
    else:
        print(f"{PARQUET_DIR} already exists. Skipping HuggingFace data extraction.")

    if not PASSAGES_CACHE_FILE.exists():
        print(f"Caching passages to {PASSAGES_CACHE_FILE}...")
        (
            pl.scan_parquet(str(PARQUET_DIR / "**/*.parquet"))
            .select(
                [
                    "document_id",
                    pl.col("text_block.text_block_id").alias("text_block_id"),
                    pl.col("text_block.language").alias("language"),
                    pl.col("text_block.type").alias("type"),
                    pl.col("text_block.type_confidence").alias("type_confidence"),
                    pl.col("text_block.coords").alias("coords"),
                    pl.col("text_block.page_number").alias("page_number"),
                    pl.col("text_block.index").alias("index"),
                    pl.col("text_block.text").alias("text"),
                ]
            )
            .filter(pl.col("text").is_not_null())
            .sort(["document_id", "index"])
            .group_by("document_id")
            .agg(
                pl.struct(
                    [
                        "text_block_id",
                        "language",
                        "type",
                        "type_confidence",
                        "coords",
                        "page_number",
                        "text",
                        "index",
                    ]
                ).alias("text_blocks")
            )
            .collect()
            .write_parquet(PASSAGES_CACHE_FILE, row_group_size=500)
        )
    else:
        print(f"{PASSAGES_CACHE_FILE} already exists. Skipping caching.")

    print(f"Passages cached at {PASSAGES_CACHE_FILE}")


def extract_data_in_api_data() -> pl.DataFrame:
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


# endregion


def _to_unix_timestamp(ts_str):
    """Safely convert ISO string to int, returns None if invalid/missing."""
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str).timestamp())
    except (ValueError, TypeError):
        return None


def _to_api_document(document: dict) -> SourceDocument:
    """Reshape a parquet row into the old API document format for the source field."""
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
                    "title": label["value"]["value"],
                },
                "timestamp": label.get("timestamp"),
            }
            for label in (document.get("labels") or [])
        ],
    }


def write_updates_file(api_documents: pl.DataFrame):
    from itertools import batched

    BATCH_SIZE = 5000
    passages_lf = pl.scan_parquet(PASSAGES_CACHE_FILE).select(
        ["document_id", "text_blocks"]
    )
    total = api_documents.height

    print(f"Writing {total} updates to {OUTPUT_FILE}...")
    with OUTPUT_FILE.open("wb") as f:
        count = 0
        t_start = time.perf_counter()

        for batch in batched(api_documents.iter_rows(named=True), BATCH_SIZE):
            batch_ids = [row["id"] for row in batch]

            print(f"Loading passages for {count}/{total} documents...")
            passage_df = passages_lf.filter(
                pl.col("document_id").is_in(batch_ids)
            ).collect()
            batch_passages: dict[str, list] = dict(
                zip(
                    passage_df["document_id"].to_list(),
                    passage_df["text_blocks"].to_list(),
                )
            )
            print(f"Loaded passages for {count}/{total} documents")
            del passage_df

            print(f"Writing {count}/{total} updates...")
            for row in batch:
                document_id = row["id"]
                huggingface_passages = batch_passages.get(document_id, [])

                passages: list[VespaPassage] = [
                    VespaPassage(
                        text_block_id=passage["text_block_id"],
                        language=passage["language"],
                        type=passage["type"],
                        type_confidence=passage["type_confidence"],
                        page_number=passage["page_number"],
                        text=passage["text"],
                    )
                    for passage in huggingface_passages
                ]

                update_op: VespaUpdateOp = {
                    "put": f"id:documents:documents::{document_id}",
                    "fields": {
                        "title": row.get("title"),
                        "description": row.get("description"),
                        "labels": [
                            {
                                "id": label["value"]["id"],
                                "type": label["value"]["type"],
                                "value": label["value"]["value"],
                                "timestamp": _to_unix_timestamp(label.get("timestamp")),
                                "relationship": label.get("type", "related"),
                            }
                            for label in (row.get("labels") or [])
                        ],
                        "passages": passages,
                        "source": orjson.dumps(
                            _to_api_document(row) | {"passages": huggingface_passages}
                        ).decode(),
                    },
                }

                f.write(orjson.dumps(update_op) + b"\n")
                count += 1

            del batch_passages
            elapsed = time.perf_counter() - t_start
            print(f"Written {count}/{total} updates ({elapsed:.1f}s)")

    print(f"Wrote {count} updates to {OUTPUT_FILE}")


def extract_vespa_updates():
    start = time.perf_counter()

    print("Extracting data-in-api data...")
    t_start = time.perf_counter()
    api_documents = extract_data_in_api_data()
    print(f"Extracted data-in-api data in {time.perf_counter() - t_start:.2f}s")

    if api_documents.is_empty():
        print("No API data found.")
        return
    print(f"Extracted {api_documents.height} documents from data-in-api.")

    print("Extracting HuggingFace data...")
    t_start = time.perf_counter()
    extract_huggingface_data()
    print(f"Extracted HuggingFace data in {time.perf_counter() - t_start:.2f}s")

    print(f"Generating updates to {OUTPUT_FILE}...")
    t_start = time.perf_counter()
    write_updates_file(api_documents)
    print(f"Generated updates to {OUTPUT_FILE} in {time.perf_counter() - t_start:.2f}s")

    print(
        f"Generated {api_documents.height} updates in {time.perf_counter() - start:.2f}s"
    )


if __name__ == "__main__":
    extract_vespa_updates()
