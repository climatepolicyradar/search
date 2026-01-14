"""
Upload a canonical set of Documents to S3 as jsonl and duckdb.

This script loads documents from a HuggingFace dataset, creates Document objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import shutil
from pathlib import Path

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


def log_disk_usage(logger, stage: str, paths: list[Path] | None = None) -> None:
    """
    Log disk usage information for debugging space issues.

    :param logger: Prefect logger instance
    :param stage: Description of the current stage/operation
    :param paths: Optional list of specific paths to check sizes for
    """
    # Get total disk usage for the root filesystem (like df -h)
    total, used, free = shutil.disk_usage("/")

    logger.info(
        f"[DISK USAGE - {stage}] Root filesystem: "
        f"Size={total // (2**30):.1f}G, "
        f"Used={used // (2**30):.1f}G, "
        f"Avail={free // (2**30):.1f}G, "
        f"Use%={100 * used / total:.0f}%"
    )

    # Log sizes of top-level directories (like du -sh /*)
    logger.info(f"[DISK USAGE - {stage}] Top-level directory sizes:")
    for item in sorted(Path("/").iterdir()):
        try:
            if item.is_dir() and not item.is_symlink():
                # Use du -sh for each directory (more efficient than Python traversal)
                import subprocess

                result = subprocess.run(
                    ["du", "-sh", str(item)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    size_str = result.stdout.split()[0]
                    logger.info(f"[DISK USAGE - {stage}]   {size_str}\t{item}")
        except (PermissionError, subprocess.TimeoutExpired):
            # Skip directories we can't access or that take too long
            pass

    # Log specific paths if provided
    if paths:
        logger.info(f"[DISK USAGE - {stage}] Specific paths:")
        for path in paths:
            if path.exists():
                if path.is_file():
                    size = path.stat().st_size
                    logger.info(
                        f"[DISK USAGE - {stage}]   {size / (2**20):.1f}M\t{path}"
                    )
                elif path.is_dir():
                    import subprocess

                    result = subprocess.run(
                        ["du", "-sh", str(path)],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        size_str = result.stdout.split()[0]
                        logger.info(f"[DISK USAGE - {stage}]   {size_str}\t{path}")
            else:
                logger.info(f"[DISK USAGE - {stage}]   (not found)\t{path}")


@task()
def get_documents_from_huggingface() -> list[Document]:
    """Get data from Huggingface, and transform it into a list of Document objects"""

    load_dotenv()

    logger = get_run_logger()

    log_disk_usage(logger, "START - Before HF download", [HF_CACHE_DIR])

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

    log_disk_usage(logger, "After HF snapshot download", [HF_CACHE_DIR, dataset_cache])

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

    log_disk_usage(logger, "After DuckDB query execution")

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

    log_disk_usage(logger, "After streaming document creation")

    documents: list[Document] = list(
        [v for v in documents_dict.values() if v is not None]
    )
    logger.info("Created %d unique documents which were valid", len(documents))

    log_disk_usage(logger, "After creating Document objects")

    return documents


@task
def upload_documents_to_s3(documents: list[Document]) -> None:
    """Upload a list of document objects to S3, for consumption by search engines"""

    logger = get_run_logger()

    log_disk_usage(logger, "START upload_documents_to_s3", [DOCUMENTS_PATH_STEM.parent])

    jsonl_path = DOCUMENTS_PATH_STEM.with_suffix(".jsonl")
    logger.info(f"Writing JSONL to {jsonl_path}")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(serialise_pydantic_list_as_jsonl(documents))
    logger.info(f"Saved {len(documents)} documents to 'data/documents.jsonl'")

    log_disk_usage(logger, "After writing JSONL file", [jsonl_path])

    # duckdb
    duckdb_path = DOCUMENTS_PATH_STEM.with_suffix(".duckdb")
    logger.info(f"Creating DuckDB at {duckdb_path}")
    create_documents_duckdb_table(duckdb_path, documents)
    logger.info(f"Saved {len(documents)} documents to '{duckdb_path}'")

    log_disk_usage(logger, "After creating DuckDB file", [jsonl_path, duckdb_path])

    logger.info("Uploading files to S3")
    upload_file_to_s3(jsonl_path)
    log_disk_usage(logger, "After uploading JSONL to S3")

    upload_file_to_s3(duckdb_path)
    log_disk_usage(logger, "After uploading DuckDB to S3")

    logger.info("Done")


@flow
def upload_documents_databases():
    """Get documents from Huggingface, and upload to required database formats in s3."""

    documents = get_documents_from_huggingface()

    upload_documents_to_s3(documents)


if __name__ == "__main__":
    upload_documents_databases()
