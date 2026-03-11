import time
from pathlib import Path

import boto3
import orjson

from prefect import flow
from search.vespa.document_indexer import (
    SourceDocument,
    typeddict_document_to_vespa_update,
)

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_CACHE_DIR = (
    REPO_ROOT_DIR / ".data_cache" / "materialize_vespa_updates/from_data_in_api"
)
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_CACHE_FILE = DATA_CACHE_DIR / "documents-latest.jsonl"
OUTPUT_FILE = DATA_CACHE_DIR / "documents-updates.jsonl"


def _extract_data() -> list[SourceDocument]:
    if not API_CACHE_FILE.exists():
        s3 = boto3.client("s3")
        s3.download_file(
            "cpr-cache",
            "pipelines/data-in-pipeline/navigator_family/documents-latest.jsonl",
            str(API_CACHE_FILE),
        )
    else:
        print(f"{API_CACHE_FILE} already exists. Skipping download.")

    with API_CACHE_FILE.open("rb") as f:
        return [orjson.loads(line) for line in f if line.strip()]


@flow(log_prints=True)
def materialize_vespa_updates_from_data_in_api():
    print("Extracting data-in-api...")
    start = time.time()
    data = _extract_data()
    print(
        f"Extracted {len(data)} documents from data-in-api ({time.time() - start:.2f}s)."
    )

    total = len(data)

    print(f"Writing {total} update_ops to {OUTPUT_FILE}...")
    start = time.time()
    with OUTPUT_FILE.open("wb") as f:
        for i, document in enumerate(data):
            update_op = typeddict_document_to_vespa_update(document)
            f.write(orjson.dumps(update_op) + b"\n")

            if i % 1000 == 0:
                print(f"Wrote {i}/{total} update_ops to {OUTPUT_FILE}.")

    print(f"Wrote {total} update_ops to {OUTPUT_FILE} ({time.time() - start:.2f}s).")

    print("Uploading to S3...")
    s3_client = boto3.client("s3")
    s3_client.upload_file(
        str(OUTPUT_FILE),
        "cpr-cache",
        "search/materialize_vespa_updates/from_data_in_api.jsonl",
    )
    print("Uploaded to S3.")


if __name__ == "__main__":
    materialize_vespa_updates_from_data_in_api()
