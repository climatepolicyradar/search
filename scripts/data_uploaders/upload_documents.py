"""
Upload a canonical set of Documents to S3 as jsonl and duckdb.

This script loads documents from a HuggingFace dataset, creates Document objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import duckdb
from dotenv import load_dotenv
from huggingface_hub import snapshot_download
from prefect import flow, get_run_logger, task

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

    dataset_cache = HF_CACHE_DIR / "datasets" / DATASET_NAME.replace("/", "--")

    logger.info(f"Downloading dataset '{DATASET_NAME}' to {dataset_cache}")
    snapshot_download(
        repo_id=DATASET_NAME,
        repo_type="dataset",
        local_dir=dataset_cache,
        token=huggingface_token,
    )

    logger.info(f"Loading dataset from {dataset_cache}")

    # Get documents by streaming through results of a duckdb query
    conn = duckdb.connect(":memory:")
    conn.execute("SET threads=2")  # Reduce parallelism to save memory
    conn.execute(
        "SET preserve_insertion_order=false"
    )  # Don't maintain order (saves memory)

    parquet_pattern = str(dataset_cache / "**/*.parquet")

    query = """
    SELECT
        document_id,
        "document_metadata.document_title" as document_title,
        "document_metadata.source_url" as source_url,
        "document_metadata.description" as description
    FROM read_parquet(?)
    WHERE "document_metadata.source_url" IS NOT NULL
    """

    logger.info("Executing DuckDB streaming query (no aggregation)")

    result = conn.execute(query, [parquet_pattern])

    documents_dict: dict[str, Document | None] = {}
    batch_size = 10_000
    total_rows_processed = 0

    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            document_id = row[0]

            # Skip if we've already seen this document_id
            if document_id in documents_dict:
                continue

            # Convert DuckDB row tuple to dict for Document.from_huggingface_row()
            row_dict = {
                "document_id": document_id,
                "document_metadata.document_title": row[1],
                "document_metadata.source_url": row[2],
                "document_metadata.description": row[3] if row[3] else "",
            }

            try:
                documents_dict[document_id] = Document.from_huggingface_row(row_dict)
            except Exception:
                logger.info(f"Failed to convert document {document_id}")
                documents_dict[document_id] = None

        total_rows_processed += len(rows)
        if total_rows_processed % 1_000_000 == 0:
            logger.info(
                f"Processed {total_rows_processed} rows, found {len(documents_dict)} unique documents so far"
            )

    conn.close()

    documents: list[Document] = list(
        [v for v in documents_dict.values() if v is not None]
    )
    logger.info("Created %d unique documents which were valid", len(documents))

    return documents


@task
def upload_documents_to_s3(documents: list[Document]) -> None:
    """Upload a list of document objects to S3, for consumption by search engines"""

    logger = get_run_logger()

    # jsonl
    jsonl_path = DOCUMENTS_PATH_STEM.with_suffix(".jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(serialise_pydantic_list_as_jsonl(documents))
    logger.info(f"Saved {len(documents)} documents to 'data/documents.jsonl'")

    # duckdb
    duckdb_path = DOCUMENTS_PATH_STEM.with_suffix(".duckdb")
    if duckdb_path.exists():
        duckdb_path.unlink()
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
