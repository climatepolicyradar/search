import logging
import os

import boto3
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
from search.config import DATA_DIR
from search.document import Document
from search.identifier import Identifier
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

# Create a mapping from row document_id to document.id for passage creation
document_id_to_doc_id: dict[str, Identifier] = {
    row_doc_id: doc.id for row_doc_id, doc in documents_dict.items()
}

passages_dataset = dataset.filter(
    lambda row: row.get("text_block.text") is not None,
    desc="Filtering rows without text",
).map(
    lambda row: {
        "passage": Passage(
            text=row["text_block.text"],
            document_id=document_id_to_doc_id[row["document_id"]],
            labels=[],
        )
    },
    desc="Creating passages",
)

passages = [item["passage"] for item in passages_dataset]


logger.info("Created %d unique documents", len(documents_dict))
logger.info("Created %d passages", len(passages))

documents_jsonl_path = DATA_DIR / "documents.jsonl"
with open(documents_jsonl_path, "w", encoding="utf-8") as f:
    f.write(serialise_pydantic_list_as_jsonl(list(documents_dict.values())))
logger.info(f"Saved {len(documents_dict)} documents to 'data/documents.jsonl'")

passages_jsonl_path = DATA_DIR / "passages.jsonl"
with open(passages_jsonl_path, "w", encoding="utf-8") as f:
    f.write(serialise_pydantic_list_as_jsonl(passages))

logger.info(f"Saved {len(passages)} passages to 'data/passages.jsonl'")

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

# duckdb
passages_duckdb_path = DATA_DIR / "passages.duckdb"
passages_duckdb_path.unlink(missing_ok=True)
conn = duckdb.connect(passages_duckdb_path)
conn.execute(
    "CREATE TABLE passages (id TEXT, text TEXT, document_id TEXT, labels TEXT[])"
)
conn.executemany(
    "INSERT INTO passages VALUES (?, ?, ?, ?)",
    [
        (passage.id, passage.text, passage.document_id, passage.labels)
        for passage in passages
    ],
)
conn.close()
logger.info(f"Saved {len(passages)} passages to '{passages_duckdb_path}'")

logger.info("Connecting to AWS")
session = boto3.Session(profile_name="labs", region_name="eu-west-1")
s3 = session.client("s3")
BUCKET_NAME = os.getenv("BUCKET_NAME")
if BUCKET_NAME is None:
    raise ValueError("BUCKET_NAME is not set")
logger.info(f"Using bucket '{BUCKET_NAME}'")

for file_path in [
    documents_jsonl_path,
    passages_jsonl_path,
    documents_duckdb_path,
    passages_duckdb_path,
]:
    s3_key = file_path.name
    s3.upload_file(str(file_path), BUCKET_NAME, s3_key)
    logger.info(f"Uploaded '{file_path}' to 's3://{BUCKET_NAME}/{s3_key}'")
