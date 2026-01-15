"""
Upload a canonical set of Passages to S3 as jsonl and duckdb.

This script loads passages from a HuggingFace dataset, creates Passage objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Note: This script recreates the document mapping internally to get document.id
values. Documents do not need to be uploaded first.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

from collections.abc import Iterator
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from huggingface_hub import snapshot_download
from prefect import flow, get_run_logger, task

from search.aws import upload_file_to_s3
from search.config import (
    DATASET_NAME,
    HF_CACHE_DIR,
    PASSAGES_PATH_STEM,
    get_from_env_with_fallback,
)
from search.passage import Passage


def read_passages_from_jsonl(jsonl_path: Path) -> Iterator[Passage]:
    """
    Stream passages from JSONL file without loading all into memory.

    :param jsonl_path: Path to the JSONL file containing passages
    :return: Iterator of Passage objects
    """
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():  # Skip empty lines
                yield Passage.model_validate_json(line.strip())


@task
def get_passages_from_huggingface() -> tuple[Path, Path]:
    """Get passages from HuggingFace and save them to JSONL and DuckDB files."""
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

    # Use DuckDB to stream passages directly from parquet files
    conn = duckdb.connect(":memory:")
    conn.execute("SET threads=2")  # Reduce parallelism to save memory
    conn.execute(
        "SET preserve_insertion_order=false"
    )  # Don't maintain order (saves memory)

    parquet_pattern = str(dataset_cache / "**/*.parquet")

    query = """
    SELECT
        document_id,
        "text_block.text" as text,
        "text_block.text_block_id" as text_block_id,
        "document_metadata.source_url" as source_url,
        "document_metadata.document_title" as document_title,
        "document_metadata.description" as description
    FROM read_parquet(?)
    WHERE "document_metadata.source_url" IS NOT NULL
        AND "text_block.text" IS NOT NULL
    """

    logger.info("Executing DuckDB streaming query")
    result = conn.execute(query, [parquet_pattern])

    jsonl_path = PASSAGES_PATH_STEM.with_suffix(".jsonl")
    duckdb_path = PASSAGES_PATH_STEM.with_suffix(".duckdb")

    batch_size = 10_000
    total_rows_processed = 0
    num_passages_created = 0

    # Stream passages and write to JSONL only (no accumulation in memory)
    logger.info("Streaming passages and writing to JSONL")
    with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break

            for row in rows:
                # Convert DuckDB row tuple to dict for Passage.from_huggingface_row()
                row_dict = {
                    "document_id": row[0],
                    "text_block.text": row[1],
                    "text_block.text_block_id": row[2] if row[2] else "",
                    "document_metadata.source_url": row[3],
                    "document_metadata.document_title": row[4],
                    "document_metadata.description": row[5] if row[5] else "",
                }

                try:
                    passage = Passage.from_huggingface_row(row_dict)
                    jsonl_file.write(passage.model_dump_json() + "\n")
                    num_passages_created += 1
                except Exception:
                    continue

            total_rows_processed += len(rows)
            if total_rows_processed % 100_000 == 0:
                logger.info(
                    f"Processed {total_rows_processed} passage rows, created {num_passages_created} passages so far"
                )

    conn.close()

    logger.info(
        f"Created {num_passages_created} passages from {total_rows_processed} rows"
    )
    logger.info(f"Saved {num_passages_created} passages to '{jsonl_path}'")

    # Create DuckDB table by reading JSONL directly (much faster than Python parsing)
    logger.info(f"Creating DuckDB table at {duckdb_path}")
    conn = duckdb.connect(str(duckdb_path))
    conn.execute(
        """
        CREATE TABLE passages AS
        SELECT
            id,
            text,
            document_id,
            labels,
            original_passage_id
        FROM read_json(?,
            format='newline_delimited',
            columns={
                'id': 'VARCHAR',
                'text': 'VARCHAR',
                'document_id': 'VARCHAR',
                'labels': 'VARCHAR[]',
                'original_passage_id': 'VARCHAR'
            }
        )
    """,
        [str(jsonl_path)],
    )
    conn.close()
    logger.info(f"Saved {num_passages_created} passages to '{duckdb_path}'")

    return jsonl_path, duckdb_path


@task
def upload_passages_to_s3(jsonl_path: Path, duckdb_path: Path) -> None:
    """Upload passage files to S3."""
    logger = get_run_logger()

    logger.info("Uploading files to S3")
    upload_file_to_s3(jsonl_path)
    upload_file_to_s3(duckdb_path)
    logger.info("Done")


@flow
def upload_passages_databases():
    """Get passages from Huggingface, and upload to required database formats in s3."""

    jsonl_path, duckdb_path = get_passages_from_huggingface()

    upload_passages_to_s3(jsonl_path, duckdb_path)


if __name__ == "__main__":
    upload_passages_databases()
