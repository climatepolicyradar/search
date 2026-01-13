"""
Upload a canonical set of Labels to S3 as jsonl and duckdb.

This script fetches all concepts from Wikibase and creates a set of Label objects.
It then saves the labels to a jsonl file and a duckdb database to a local data directory.
Finally, it uploads the files to S3 using the `BUCKET_NAME` environment variable.

Take a look at infra/README.md for instructions on how to set the `BUCKET_NAME`
environment variable.
"""

from dotenv import load_dotenv
from knowledge_graph.wikibase import WikibaseSession
from prefect import flow, get_run_logger, task

from search.aws import get_ssm_parameter, upload_file_to_s3
from search.config import LABELS_PATH_STEM
from search.engines.duckdb import create_labels_duckdb_table
from search.engines.json import serialise_pydantic_list_as_jsonl
from search.label import Label


@task
def get_labels_from_wikibase() -> list[Label]:
    """Get labels from Wikibase and transform them into Label objects."""
    load_dotenv()

    logger = get_run_logger()

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
                source="wikibase",
                id_at_source=str(concept.wikibase_id),
            )
        )

    logger.info(f"Created a set of {len(labels)} labels from concepts")

    return labels


@task
def upload_labels_to_s3(labels: list[Label]) -> None:
    """Upload a list of label objects to S3, for consumption by search engines."""
    logger = get_run_logger()

    jsonl_path = LABELS_PATH_STEM.with_suffix(".jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(serialise_pydantic_list_as_jsonl(labels))

    logger.info(f"Saved {len(labels)} labels to '{jsonl_path}'")

    duckdb_path = LABELS_PATH_STEM.with_suffix(".duckdb")
    create_labels_duckdb_table(duckdb_path, labels)
    logger.info(f"Saved {len(labels)} labels to '{duckdb_path}'")

    logger.info("Uploading datasets to S3")
    upload_file_to_s3(jsonl_path)
    upload_file_to_s3(duckdb_path)
    logger.info("Done")


@flow
def upload_labels_databases():
    """Get labels from Wikibase, and upload to required database formats in s3."""

    labels = get_labels_from_wikibase()

    upload_labels_to_s3(labels)


if __name__ == "__main__":
    upload_labels_databases()
