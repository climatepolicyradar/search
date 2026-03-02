import subprocess
import time
from pathlib import Path
from typing import TypedDict

import boto3
import orjson

from prefect import flow

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[1]

DATA_CACHE_DIR = (
    REPO_ROOT_DIR / ".data_cache" / "materialize_vespa_updates/from_indexer_input"
)
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_CACHE_DIR / "documents-updates.jsonl"


class Passage(TypedDict):
    text_block_id: str
    text: str
    language: str
    type: str
    type_confidence: float
    page_number: int
    heading_id: str | None

    # These need work
    # pages: list[dict] | None
    # spans: list[dict] | None
    # concepts: list[dict] | None


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


def _extract_data():
    if not (DATA_CACHE_DIR / "indexer_input").exists():
        subprocess.run(
            [
                "aws",
                "s3",
                "sync",
                "s3://cpr-prod-data-pipeline-cache/indexer_input/",
                str(DATA_CACHE_DIR / "indexer_input"),
                "--exclude",
                "*",
                "--include",
                "*.json",
            ],
            check=True,
        )

    files = list((DATA_CACHE_DIR / "indexer_input").glob("*.json"))
    return files


@flow(log_prints=True)
def materialize_vespa_updates_from_indexer_input():
    print("Extracting data...")
    start = time.time()
    data = _extract_data()
    print(f"Extracted {len(data)} documents ({time.time() - start:.2f}s).")

    total = len(data)

    print(f"Writing {total} update_ops to {OUTPUT_FILE}...")
    start = time.time()
    with OUTPUT_FILE.open("wb") as f:
        for i, file in enumerate(data):
            with open(file, "rb") as passage_file:
                document = orjson.loads(passage_file.read())
                if not document:
                    continue

                text_blocks = (document.get("pdf_data") or {}).get("text_blocks", [])
                passages: list[Passage] = []
                for text_block in text_blocks:
                    passages.append(
                        {
                            "text_block_id": text_block["text_block_id"],
                            "language": text_block["language"],
                            "type": text_block["type"],
                            "type_confidence": text_block["type_confidence"],
                            "page_number": text_block["page_number"],
                            "text": ". ".join(text_block["text"]),
                            "heading_id": text_block.get("heading_id"),
                        }
                    )

                update_op = {
                    "update": f"id:documents:documents::{document.get('id')}",
                    "fields": {
                        "passages": {"assign": passages},
                    },
                }
                f.write(orjson.dumps(update_op) + b"\n")

                if i % 1000 == 0:
                    print(
                        f"Wrote {i}/{total} update_ops to {OUTPUT_FILE} ({time.time() - start:.2f}s)."
                    )

    print(f"Wrote {total} update_ops to {OUTPUT_FILE} ({time.time() - start:.2f}s).")

    print("Uploading to S3...")
    s3_client = boto3.client("s3")
    s3_client.upload_file(
        str(OUTPUT_FILE),
        "cpr-cache",
        "search/materialize_vespa_updates/from_indexer_input.jsonl",
    )
    print("Uploaded to S3.")


if __name__ == "__main__":
    materialize_vespa_updates_from_indexer_input()
