"""
Upload a canonical set of Labels to S3 as jsonl and duckdb.

This script fetches all concepts from Wikibase and creates a set of Label objects.
It then saves the labels to a jsonl file and a duckdb database to a local data directory.
Finally, it uploads the files to S3 using the `BUCKET_NAME` environment variable.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import logging
import os
from pathlib import Path

import boto3
import duckdb
from dotenv import load_dotenv
from knowledge_graph.wikibase import WikibaseSession
from rich.logging import RichHandler

from search.label import Label

load_dotenv()

data_dir = Path("data")
data_dir.mkdir(parents=True, exist_ok=True)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler())


session = boto3.Session(profile_name="labs", region_name="eu-west-1")
logger.info("Connected to AWS")

s3 = session.client("s3")
BUCKET_NAME = os.getenv("BUCKET_NAME")
if BUCKET_NAME is None:
    raise ValueError("BUCKET_NAME is not set")
logger.info(f"Using bucket '{BUCKET_NAME}'")


ssm = session.client("ssm")
logger.info("Connected to AWS SSM")


def get_parameter(name: str) -> str:
    response = ssm.get_parameter(
        Name=name,
        WithDecryption=True,
    )
    return response["Parameter"]["Value"]


username = get_parameter("/Wikibase/Cloud/ServiceAccount/Username")
password = get_parameter("/Wikibase/Cloud/ServiceAccount/Password")
url = get_parameter("/Wikibase/Cloud/URL")
logger.info("Fetched wikibase credentials from AWS SSM")

wikibase = WikibaseSession(url=url, username=username, password=password)
logger.info(f"Connected to Wikibase: {wikibase}")

all_concepts = wikibase.get_concepts()
logger.info(f"Found {len(all_concepts)} concepts in Wikibase")

labels: list[Label] = []
for concept in all_concepts:
    labels.append(
        Label(
            preferred_label=concept.preferred_label,
            alternative_labels=concept.alternative_labels,
            negative_labels=concept.negative_labels,
            description=concept.description,
        )
    )

logger.info(f"Created a set of {len(labels)} labels from concepts")

jsonl_path = data_dir / "labels.jsonl"
with open(jsonl_path, "w", encoding="utf-8") as f:
    for label in labels:
        f.write(label.model_dump_json() + "\n")

logger.info(f"Saved {len(labels)} labels to '{jsonl_path}'")

duckdb_path = data_dir / "labels.duckdb"
duckdb_path.unlink(missing_ok=True)
conn = duckdb.connect(duckdb_path)
conn.execute(
    "CREATE TABLE labels (id TEXT, preferred_label TEXT, alternative_labels TEXT[], negative_labels TEXT[], description TEXT)"
)
conn.executemany(
    "INSERT INTO labels VALUES (?, ?, ?, ?, ?)",
    [
        (
            label.id,
            label.preferred_label,
            label.alternative_labels,
            label.negative_labels,
            label.description,
        )
        for label in labels
    ],
)
conn.close()
logger.info(f"Saved {len(labels)} labels to '{duckdb_path}'")


logger.info("Uploading datasets to S3")
s3.upload_file(jsonl_path, BUCKET_NAME, "labels.jsonl")
logger.info(f"Uploaded '{jsonl_path}' to 's3://{BUCKET_NAME}/labels.jsonl'")

s3.upload_file(duckdb_path, BUCKET_NAME, "labels.duckdb")
logger.info(f"Uploaded '{duckdb_path}' to 's3://{BUCKET_NAME}/labels.duckdb'")
logger.info("Done")
