import time
from pathlib import Path
from typing import TypedDict
from huggingface_hub import snapshot_download
import requests
import os
import orjson
import polars as pl
from datetime import datetime
from dotenv import load_dotenv


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

PASSAGES_CACHE_FILE = DATA_CACHE_DIR / "build_vespa_updates" / "passages_cache.parquet"
PASSAGES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_CACHE_DIR / "build_vespa_updates" / "updates.jsonl"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

load_dotenv()


# region Types
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

    if not PASSAGES_CACHE_FILE.exists():
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
    api_documents: list[Document], passages_map: dict[str, list[HuggingFaceTextBlock]]
):
    BATCH_SIZE = 5000
    with OUTPUT_FILE.open("wb") as f:
        count = 0
        batch = []

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
                        }
                        for label in document.get("labels", [])
                    ],
                    "passages": passages,
                    "source": orjson.dumps(
                        document | {"passages": huggingface_passages}  # type: ignore
                    ).decode(),
                },
            }

            batch.append(orjson.dumps(update_op))
            count += 1

            if len(batch) >= BATCH_SIZE:
                f.write(b"\n".join(batch) + b"\n")
                batch = []

        if batch:
            f.write(b"\n".join(batch) + b"\n")


def build_vespa_updates():
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
    build_vespa_updates()
