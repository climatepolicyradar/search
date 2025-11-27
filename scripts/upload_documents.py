"""
Upload a canonical set of Documents to S3 as jsonl and duckdb.

This script loads documents from a HuggingFace dataset, creates Document objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import logging

import duckdb
from datasets import load_dataset
from dotenv import load_dotenv
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from scripts import serialise_pydantic_list_as_jsonl
from search.aws import upload_file_to_s3
from search.config import DATA_DIR
from search.document import Document

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

# Track documents by document_id to avoid duplicates
documents_dict: dict[str, Document] = {}

progress_bar = Progress(
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    TimeRemainingColumn(),
)

with progress_bar:
    task = progress_bar.add_task("Creating documents", total=len(dataset))
    for idx, row in enumerate(dataset):
        progress_bar_kwargs: dict[str, int | str] = {"advance": 1}
        if idx % 10_000 == 0:
            progress_bar_kwargs["description"] = (
                f"Found {len(documents_dict)} documents"
            )
        progress_bar.update(task, **progress_bar_kwargs)

        document_id = row["document_id"]

        # If we haven't seen this document_id before, create a new Document object
        if document_id not in documents_dict:
            title = row.get("document_metadata.document_title") or document_id
            source_url = row.get("document_metadata.source_url")
            description = row.get("document_metadata.description") or ""

            documents_dict[document_id] = Document(
                title=title,
                source_url=source_url,
                description=description,
                labels=[],  # deliberately leaving this empty for now
            )

logger.info("Created %d unique documents", len(documents_dict))

documents_jsonl_path = DATA_DIR / "documents.jsonl"
with open(documents_jsonl_path, "w", encoding="utf-8") as f:
    f.write(serialise_pydantic_list_as_jsonl(list(documents_dict.values())))
logger.info(f"Saved {len(documents_dict)} documents to 'data/documents.jsonl'")

# duckdb
documents_duckdb_path = DATA_DIR / "documents.duckdb"
documents_duckdb_path.unlink(missing_ok=True)
conn = duckdb.connect(documents_duckdb_path)
conn.execute(
    "CREATE TABLE documents (id TEXT, title TEXT, source_url TEXT, description TEXT)"
)
conn.executemany(
    "INSERT INTO documents VALUES (?, ?, ?, ?)",
    [
        (document.id, document.title, str(document.source_url), document.description)
        for document in documents_dict.values()
    ],
)
conn.close()
logger.info(f"Saved {len(documents_dict)} documents to '{documents_duckdb_path}'")

logger.info("Uploading files to S3")
upload_file_to_s3(documents_jsonl_path)
upload_file_to_s3(documents_duckdb_path)
logger.info("Done")
