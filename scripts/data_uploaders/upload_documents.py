"""
Upload a canonical set of Documents to S3 as jsonl and duckdb.

This script loads documents from a HuggingFace dataset, creates Document objects,
saves them to jsonl and duckdb files, and uploads them to S3.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import shutil
from pathlib import Path

from datasets import Dataset, load_dataset
from dotenv import load_dotenv
from huggingface_hub import snapshot_download
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
    dataset = load_dataset(str(dataset_cache), split="train")
    assert isinstance(dataset, Dataset), (
        "dataset from huggingface should be of type Dataset"
    )
    logger.info(f"Loaded {len(dataset)} rows")

    log_disk_usage(logger, "After loading dataset into memory")

    dataset = dataset.filter(
        lambda row: row.get("document_metadata.source_url") is not None,
        desc="Filtering rows without source_url",
    )
    logger.info(f"Filtered to {len(dataset)} rows with source_url")

    log_disk_usage(logger, "After filtering dataset")

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
