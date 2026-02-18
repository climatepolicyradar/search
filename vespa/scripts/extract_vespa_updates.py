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

import orjson
import polars as pl
import requests
from dotenv import load_dotenv
from huggingface_hub import snapshot_download

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_CACHE_DIR = REPO_ROOT_DIR / ".data_cache"
API_CACHE_FILE = DATA_CACHE_DIR / "data-in-api" / "documents.json"
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


class Label(TypedDict):
    id: int
    type: str
    title: str


class DocumentLabelRelationship(TypedDict):
    label: Label
    timestamp: str | None


class Document(TypedDict, total=False):
    id: str
    title: str | None
    description: str | None
    labels: list[DocumentLabelRelationship]


class VespaLabel(TypedDict):
    id: int
    type: str
    title: str
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


# endregion


# region Extract
def extract_huggingface_data() -> dict[str, list[HuggingFaceTextBlock]]:
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
            .write_parquet(PASSAGES_CACHE_FILE)
        )
    else:
        print(f"{PASSAGES_CACHE_FILE} already exists. Skipping caching.")

    print(f"Loading passages from {PASSAGES_CACHE_FILE}")
    df = pl.read_parquet(PASSAGES_CACHE_FILE)

    return {row["document_id"]: row["text_blocks"] for row in df.iter_rows(named=True)}


def extract_data_in_api_data() -> list[Document]:
    if API_CACHE_FILE.exists():
        print(f"{API_CACHE_FILE} already exists. Skipping caching.")
        return orjson.loads(API_CACHE_FILE.read_bytes()).get("data", [])

    API_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    page = 1
    documents = []

    with requests.Session() as session:
        while True:
            print(f"fetching page {page} from data-in api")
            response = session.get(
                "https://api.climatepolicyradar.org/data-in/documents",
                params={"page": page, "page_size": 100},
            )
            response.raise_for_status()
            batch = response.json().get("data", [])

            if not batch:
                break

            documents.extend(batch)
            page += 1

    API_CACHE_FILE.write_bytes(orjson.dumps({"data": documents}))
    return documents


# endregion


def _to_unix_timestamp(ts_str):
    """Safely convert ISO string to int, returns None if invalid/missing."""
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str).timestamp())
    except (ValueError, TypeError):
        return None


def write_updates_file(
    api_documents: list[Document],
    passages_map: dict[str, list[HuggingFaceTextBlock]],
):
    print(f"Writing updates to {OUTPUT_FILE}...")

    if not api_documents:
        print("No API documents to write.")
        return

    with OUTPUT_FILE.open("wb") as f:
        total_count = 0

        for document in api_documents:
            document_id = document.get("id")
            if not document_id:
                continue

            huggingface_passages = passages_map.get(document_id, [])

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
                    "title": document.get("title"),
                    "description": document.get("description"),
                    "labels": [
                        {
                            "id": label["label"]["id"],
                            "type": label["label"]["type"],
                            "title": label["label"]["title"],
                            "timestamp": _to_unix_timestamp(label.get("timestamp")),
                            "relationship": label.get("type", "related"),
                        }
                        for label in document.get("labels", [])
                    ],
                    "passages": passages,
                    "source": orjson.dumps(
                        document | {"passages": huggingface_passages}  # type: ignore
                    ).decode(),
                },
            }

            f.write(orjson.dumps(update_op) + b"\n")
            total_count += 1

            if total_count % 5000 == 0:
                print(f"Wrote {total_count} updates...")

    print(f"Wrote total {total_count} updates")


def extract_vespa_updates():
    start = time.perf_counter()

    print("Extracting data-in-api data...")
    t_start = time.perf_counter()
    api_documents = extract_data_in_api_data()
    print(f"Extracted data-in-api data in {time.perf_counter() - t_start:.2f}s")

    if not api_documents:
        print("No API data found.")
        return
    print(f"Extracted {len(api_documents)} documents from data-in-api.")

    print("Extracting HuggingFace data...")
    t_start = time.perf_counter()
    passages_map = extract_huggingface_data()
    print(f"Extracted HuggingFace data in {time.perf_counter() - t_start:.2f}s")

    print(f"Generating updates to {OUTPUT_FILE}...")
    t_start = time.perf_counter()
    write_updates_file(api_documents, passages_map)
    print(f"Generated updates to {OUTPUT_FILE} in {time.perf_counter() - t_start:.2f}s")

    print(
        f"Generated {len(api_documents)} updates in {time.perf_counter() - start:.2f}s"
    )


if __name__ == "__main__":
    extract_vespa_updates()
