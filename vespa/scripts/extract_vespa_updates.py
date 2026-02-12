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
def ensure_huggingface_cache_exists() -> None:
    """
    Ensures HuggingFace data is downloaded and cached to parquet.

    Downloads from HuggingFace if needed and creates an aggregated passages
    cache file grouped by document_id.
    """
    parquet_files_exist = len(list(PARQUET_DIR.glob("**/*.parquet"))) > 0
    if PARQUET_DIR.exists() and parquet_files_exist:
        print(f"{PARQUET_DIR} already exists. Skipping HuggingFace data extraction.")
    else:
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id="climatepolicyradar/all-document-text-data-weekly",
            repo_type="dataset",
            local_dir=PARQUET_DIR,
            token=os.getenv("HUGGINGFACE_TOKEN"),
        )

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
                )
                .sort_by("index")
                .alias("text_blocks")
            )
            .sink_parquet(PASSAGES_CACHE_FILE)
        )
    else:
        print(f"{PASSAGES_CACHE_FILE} already exists. Skipping caching.")


def get_passages_for_documents(
    document_ids: list[str],
) -> dict[str, list[HuggingFaceTextBlock]]:
    """
    Retrieves passages for a batch of documents from the cache.

    Uses lazy evaluation to load only the requested documents into memory.

    :param document_ids: List of document IDs to fetch passages for.
    :returns: Dict mapping document_id to list of text blocks.
    """
    df = (
        pl.scan_parquet(PASSAGES_CACHE_FILE)
        .filter(pl.col("document_id").is_in(document_ids))
        .collect()
    )
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


def write_updates_file(api_documents: list[Document]):
    """
    Writes Vespa update operations to a JSONL file.

    Processes documents in chunks to avoid loading all passage data into memory.

    :param api_documents: List of documents from the API.
    """
    WRITE_BATCH_SIZE = 5000
    CHUNK_SIZE = 1000  # Number of documents to load passages for at once
    print(f"Writing updates to {OUTPUT_FILE}...")
    total_chunks = (len(api_documents) + CHUNK_SIZE - 1) // CHUNK_SIZE

    with OUTPUT_FILE.open("wb") as f:
        count = 0
        write_batch = []

        # Process api_documents in chunks to limit memory usage
        for chunk_idx, chunk_start in enumerate(
            range(0, len(api_documents), CHUNK_SIZE)
        ):
            print(f"Processing chunk {chunk_idx + 1}/{total_chunks}...", flush=True)
            chunk_end = min(chunk_start + CHUNK_SIZE, len(api_documents))
            chunk = api_documents[chunk_start:chunk_end]

            # Get document IDs for this chunk (filter out None values)
            chunk_doc_ids = [
                doc_id for doc in chunk if (doc_id := doc.get("id")) is not None
            ]

            # Load only passages for this chunk
            passages_map = get_passages_for_documents(chunk_doc_ids)

            for document in chunk:
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
                    # ID Format: id:documents:documents::<doc_id>
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

                write_batch.append(orjson.dumps(update_op))
                count += 1

                if len(write_batch) >= WRITE_BATCH_SIZE:
                    print("Writing batch to disk...")
                    f.write(b"\n".join(write_batch) + b"\n")
                    write_batch = []

        if write_batch:
            f.write(b"\n".join(write_batch) + b"\n")

    print(f"Wrote {count} updates to {OUTPUT_FILE}")


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

    print("Ensuring HuggingFace cache exists...")
    t_start = time.perf_counter()
    ensure_huggingface_cache_exists()
    print(f"HuggingFace cache ready in {time.perf_counter() - t_start:.2f}s")

    print(f"Generating updates to {OUTPUT_FILE}...")
    t_start = time.perf_counter()
    write_updates_file(api_documents)
    print(f"Generated updates to {OUTPUT_FILE} in {time.perf_counter() - t_start:.2f}s")

    print(
        f"Generated {len(api_documents)} updates in {time.perf_counter() - start:.2f}s"
    )


if __name__ == "__main__":
    extract_vespa_updates()
