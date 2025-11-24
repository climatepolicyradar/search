import logging
import os

import boto3
import duckdb
from datasets import load_dataset
from dotenv import load_dotenv
from rich.logging import RichHandler
from rich.progress import track

from search.config import DATA_DIR
from search.document import Document
from search.passage import Passage

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler())

DATASET_NAME = "climatepolicyradar/all-document-text-data"

dataset = load_dataset(DATASET_NAME, split="train")


# Track documents by document_id to avoid duplicates
documents_dict: dict[str, Document] = {}
# Track document IDs that were skipped due to missing URL
skipped_document_ids: set[str] = set()
passages: list[Passage] = []

for row in track(dataset.select(range(10_000)), description="Parsing passages"):
    document_id = row["document_id"]
    # Skip if we've already seen this document_id and it was skipped
    if document_id in skipped_document_ids:
        continue

    # If we haven't seen this document_id before, create a new Document object
    if document_id not in documents_dict:
        title = row.get("document_metadata.document_title") or document_id
        source_url = row.get("document_metadata.source_url")
        description = row.get("document_metadata.description") or ""

        # Skip the document if its source_url is missing
        if not source_url:
            logger.warning(
                f"Skipping document '{document_id}' (title: '{title}') - missing source_url",
            )
            skipped_document_ids.add(document_id)
            continue

        documents_dict[document_id] = Document(
            title=title,
            source_url=source_url,
            description=description,
            labels=[],  # deliberately leaving this empty for now
        )

    document = documents_dict[document_id]

    # Only create a passage if it has text content
    if text := row.get("text_block.text"):
        passages.append(
            Passage(
                text=text,
                document_id=document.id,
                labels=[],  # deliberately leaving this empty for now
            )
        )


logger.info("Created %d unique documents", len(documents_dict))
logger.info("Created %d passages", len(passages))
if skipped_document_ids:
    logger.info(
        "Skipped %d documents due to missing source_url", len(skipped_document_ids)
    )

documents_jsonl_path = DATA_DIR / "documents.jsonl"
with open(documents_jsonl_path, "w", encoding="utf-8") as f:
    for document in documents_dict.values():
        f.write(document.model_dump_json() + "\n")
logger.info(f"Saved {len(documents_dict)} documents to 'data/documents.jsonl'")

passages_jsonl_path = DATA_DIR / "passages.jsonl"
with open(passages_jsonl_path, "w", encoding="utf-8") as f:
    for passage in passages:
        f.write(passage.model_dump_json() + "\n")

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
