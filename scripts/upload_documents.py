"""
Upload a canonical set of Documents to S3 as jsonl and duckdb.

This script loads documents from a HuggingFace dataset, creates Document objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

from datasets import Dataset, load_dataset
from dotenv import load_dotenv
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from search.aws import upload_file_to_s3
from search.config import DATA_DIR, DATASET_NAME
from search.document import Document
from search.engines.duckdb import create_documents_duckdb_table
from search.engines.json import serialise_pydantic_list_as_jsonl
from search.logging import get_logger

load_dotenv()

logger = get_logger(__name__)


logger.info(f"Loading dataset '{DATASET_NAME}'")
dataset = load_dataset(DATASET_NAME, split="train")
assert isinstance(dataset, Dataset), (
    "dataset from huggingface should be of type Dataset"
)
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
        progress_bar.update(task, **progress_bar_kwargs)  # type: ignore

        document_id = row["document_id"]

        # If we haven't seen this document_id before, create a new Document object
        if document_id not in documents_dict:
            documents_dict[document_id] = Document.from_huggingface_row(row)


documents: list[Document] = list(documents_dict.values())
logger.info("Created %d unique documents", len(documents))

documents_jsonl_path = DATA_DIR / "documents.jsonl"
with open(documents_jsonl_path, "w", encoding="utf-8") as f:
    f.write(serialise_pydantic_list_as_jsonl(documents))
logger.info(f"Saved {len(documents)} documents to 'data/documents.jsonl'")

# duckdb
documents_duckdb_path = DATA_DIR / "documents.duckdb"
create_documents_duckdb_table(documents_duckdb_path, documents)
logger.info(f"Saved {len(documents)} documents to '{documents_duckdb_path}'")

logger.info("Uploading files to S3")
upload_file_to_s3(documents_jsonl_path)
upload_file_to_s3(documents_duckdb_path)
logger.info("Done")
