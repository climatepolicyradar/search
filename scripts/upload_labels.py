"""
Upload a canonical set of Labels to S3 as jsonl and duckdb.

This script fetches all concepts from Wikibase and creates a set of Label objects.
It then saves the labels to a jsonl file and a duckdb database to a local data directory.
Finally, it uploads the files to S3 using the `BUCKET_NAME` environment variable.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

import logging

from dotenv import load_dotenv
from knowledge_graph.wikibase import WikibaseSession
from rich.logging import RichHandler

from scripts import serialise_pydantic_list_as_jsonl
from search.aws import get_ssm_parameter, upload_file_to_s3
from search.config import DATA_DIR
from search.engines.duckdb import create_labels_duckdb_table
from search.label import Label

load_dotenv()


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler())

username = get_ssm_parameter("/Wikibase/Cloud/ServiceAccount/Username")
password = get_ssm_parameter("/Wikibase/Cloud/ServiceAccount/Password")
url = get_ssm_parameter("/Wikibase/Cloud/URL")
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

jsonl_path = DATA_DIR / "labels.jsonl"
with open(jsonl_path, "w", encoding="utf-8") as f:
    f.write(serialise_pydantic_list_as_jsonl(labels))

logger.info(f"Saved {len(labels)} labels to '{jsonl_path}'")

duckdb_path = DATA_DIR / "labels.duckdb"
create_labels_duckdb_table(duckdb_path, labels)
logger.info(f"Saved {len(labels)} labels to '{duckdb_path}'")


logger.info("Uploading datasets to S3")
upload_file_to_s3(jsonl_path)
upload_file_to_s3(duckdb_path)
logger.info("Done")
