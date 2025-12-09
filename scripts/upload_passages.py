"""
Upload a canonical set of Passages to S3 as jsonl and duckdb.

This script loads passages from a HuggingFace dataset, creates Passage objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Note: This script recreates the document mapping internally to get document.id
values. Documents do not need to be uploaded first.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import logging
from collections.abc import Iterator

from datasets import Dataset, load_dataset
from dotenv import load_dotenv
from rich.logging import RichHandler
from rich.progress import track

from search.aws import upload_file_to_s3
from search.config import DATA_DIR, DATASET_NAME
from search.engines.duckdb import create_passages_duckdb_table
from search.passage import Passage

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler())

logger.info(f"Loading dataset '{DATASET_NAME}'")
dataset = load_dataset(DATASET_NAME, split="train")
assert isinstance(dataset, Dataset), (
    "dataset from huggingface should be of type Dataset"
)
logger.info(f"Loaded {len(dataset)} rows")

dataset = dataset.filter(
    lambda row: row.get("document_metadata.source_url") is not None
    and row.get("text_block.text") is not None,
    desc="Filtering rows without source_url or text",
)
logger.info(f"Filtered to {len(dataset)} rows with source_url and text")

passages_jsonl_path = DATA_DIR / "passages.jsonl"
passages_duckdb_path = DATA_DIR / "passages.duckdb"


def generate_passages() -> Iterator[Passage]:
    """Generate Passage objects from the dataset, writing to JSONL as we go."""
    with open(passages_jsonl_path, "w", encoding="utf-8") as jsonl_file:
        for row in track(dataset, description="Creating passages"):
            passage = Passage.from_huggingface_row(row)
            jsonl_file.write(passage.model_dump_json() + "\n")
            yield passage


create_passages_duckdb_table(passages_duckdb_path, generate_passages())

with open(passages_jsonl_path, "r", encoding="utf-8") as f:
    num_passages = sum(1 for _ in f)

logger.info(f"Saved {num_passages} passages to '{passages_jsonl_path}'")
logger.info(f"Saved {num_passages} passages to '{passages_duckdb_path}'")

logger.info("Uploading files to S3")
upload_file_to_s3(passages_jsonl_path)
upload_file_to_s3(passages_duckdb_path)
logger.info("Done")
