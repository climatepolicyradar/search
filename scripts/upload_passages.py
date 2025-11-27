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

from datasets import load_dataset
from dotenv import load_dotenv
from rich.logging import RichHandler

from scripts import serialise_pydantic_list_as_jsonl
from search.aws import upload_file_to_s3
from search.config import DATA_DIR
from search.document import Document
from search.engines.duckdb import create_passages_duckdb_table
from search.passage import Passage

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler())

DATASET_NAME = "climatepolicyradar/all-document-text-data"

logger.info(f"Loading dataset '{DATASET_NAME}'")
dataset = load_dataset(DATASET_NAME, split="train")
logger.info(f"Loaded {len(dataset)} rows")

dataset = dataset.filter(
    lambda row: row.get("document_metadata.source_url") is not None,
    desc="Filtering rows without source_url",
)
logger.info(f"Filtered to {len(dataset)} rows with source_url")

passages_dataset = dataset.filter(
    lambda row: row.get("text_block.text") is not None,
    desc="Filtering rows without text",
).map(
    lambda row: {
        "passage": Passage(
            text=row["text_block.text"],
            document_id=Document(
                title=row.get("document_metadata.document_title") or row["document_id"],
                source_url=row["document_metadata.source_url"],
                description=row.get("document_metadata.description") or "",
                labels=[],
            ).id,
            labels=[],  # deliberately leaving this empty for now
        )
    },
    desc="Creating passages",
)

passages = [item["passage"] for item in passages_dataset]

logger.info("Created %d passages", len(passages))

passages_jsonl_path = DATA_DIR / "passages.jsonl"
with open(passages_jsonl_path, "w", encoding="utf-8") as f:
    f.write(serialise_pydantic_list_as_jsonl(passages))

logger.info(f"Saved {len(passages)} passages to 'data/passages.jsonl'")

# duckdb
passages_duckdb_path = DATA_DIR / "passages.duckdb"
create_passages_duckdb_table(passages_duckdb_path, passages)
logger.info(f"Saved {len(passages)} passages to '{passages_duckdb_path}'")

logger.info("Uploading files to S3")
upload_file_to_s3(passages_jsonl_path)
upload_file_to_s3(passages_duckdb_path)
logger.info("Done")
