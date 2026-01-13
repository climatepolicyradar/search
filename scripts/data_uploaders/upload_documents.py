"""
Upload a canonical set of Documents to S3 as jsonl and duckdb.

This script loads documents from a HuggingFace dataset, creates Document objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

from datasets import Dataset, load_dataset
from dotenv import load_dotenv
from prefect import flow, get_run_logger, task
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from search.aws import upload_file_to_s3
from search.config import (
    DATASET_NAME,
    DOCUMENTS_PATH_STEM,
    HF_CACHE_DIR,
    get_from_env_with_fallback,
)
from search.document import Document
from search.engines.duckdb import create_documents_duckdb_table
from search.engines.json import serialise_pydantic_list_as_jsonl


@task()
def get_documents_from_huggingface() -> list[Document]:
    """Get data from Huggingface, and transform it into a list of Document objects"""

    load_dotenv()

    logger = get_run_logger()

    huggingface_token = get_from_env_with_fallback(
        var_name="HUGGINGFACE_TOKEN", ssm_name="/Huggingface/Token"
    )

    logger.info(f"Loading dataset '{DATASET_NAME}'")
    dataset = load_dataset(
        DATASET_NAME,
        split="train",
        token=huggingface_token,
        cache_dir=str(HF_CACHE_DIR),
    )
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
        progress_task = progress_bar.add_task("Creating documents", total=len(dataset))
        for idx, row in enumerate(dataset):
            progress_bar_kwargs: dict[str, int | str] = {"advance": 1}
            if idx % 10_000 == 0:
                progress_bar_kwargs["description"] = (
                    f"Found {len(documents_dict)} documents"
                )
            progress_bar.update(progress_task, **progress_bar_kwargs)  # type: ignore

            document_id = row["document_id"]

            # If we haven't seen this document_id before, create a new Document object
            if document_id not in documents_dict:
                documents_dict[document_id] = Document.from_huggingface_row(row)

    documents: list[Document] = list(documents_dict.values())
    logger.info("Created %d unique documents", len(documents))

    return documents


@task
def upload_documents_to_s3(documents: list[Document]) -> None:
    """Upload a list of document objects to S3, for consumption by search engines"""

    logger = get_run_logger()

    jsonl_path = DOCUMENTS_PATH_STEM.with_suffix(".jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(serialise_pydantic_list_as_jsonl(documents))
    logger.info(f"Saved {len(documents)} documents to 'data/documents.jsonl'")

    # duckdb
    duckdb_path = DOCUMENTS_PATH_STEM.with_suffix(".duckdb")
    create_documents_duckdb_table(duckdb_path, documents)
    logger.info(f"Saved {len(documents)} documents to '{duckdb_path}'")

    logger.info("Uploading files to S3")
    upload_file_to_s3(jsonl_path)
    upload_file_to_s3(duckdb_path)
    logger.info("Done")


@flow
def upload_documents_databases():
    """Get documents from Huggingface, and upload to required database formats in s3."""

    documents = get_documents_from_huggingface()

    upload_documents_to_s3(documents)


if __name__ == "__main__":
    upload_documents_databases()
