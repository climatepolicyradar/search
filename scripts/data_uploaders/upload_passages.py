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

from datasets import Dataset, load_dataset
from dotenv import load_dotenv
from prefect import flow, task
from rich.progress import track

from search.aws import upload_file_to_s3
from search.config import DATASET_NAME, PASSAGES_PATH_STEM
from search.engines.duckdb import create_passages_duckdb_table
from search.logging import get_logger
from search.passage import Passage


@task
def get_passages_from_huggingface() -> tuple[Path, Path]:
    """Get passages from HuggingFace and save them to JSONL and DuckDB files."""
    load_dotenv()

    logger = get_logger(__name__)

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

    jsonl_path = PASSAGES_PATH_STEM.with_suffix(".jsonl")
    duckdb_path = PASSAGES_PATH_STEM.with_suffix(".duckdb")

    def generate_passages() -> Iterator[Passage]:
        """Generate Passage objects from the dataset, writing to JSONL as we go."""
        with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
            for row in track(dataset, description="Creating passages"):
                passage = Passage.from_huggingface_row(row)
                jsonl_file.write(passage.model_dump_json() + "\n")
                yield passage

    create_passages_duckdb_table(duckdb_path, generate_passages())

    with open(jsonl_path, "r", encoding="utf-8") as f:
        num_passages = sum(1 for _ in f)

    logger.info(f"Saved {num_passages} passages to '{jsonl_path}'")
    logger.info(f"Saved {num_passages} passages to '{duckdb_path}'")

    return jsonl_path, duckdb_path


@task
def upload_passages_to_s3(jsonl_path: Path, duckdb_path: Path) -> None:
    """Upload passage files to S3."""
    logger = get_logger(__name__)

    logger.info("Uploading files to S3")
    upload_file_to_s3(jsonl_path)
    upload_file_to_s3(duckdb_path)
    logger.info("Done")


@flow
def main():
    """Main execution function for uploading passages."""

    jsonl_path, duckdb_path = get_passages_from_huggingface()

    upload_passages_to_s3(jsonl_path, duckdb_path)


if __name__ == "__main__":
    main()
