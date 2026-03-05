import subprocess
import time
from pathlib import Path

import boto3
import orjson

from prefect import flow
from search.vespa.concepts_indexer import index

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]

DATA_CACHE_DIR = (
    REPO_ROOT_DIR / ".data_cache" / "materialize_vespa_updates/from_inference_results"
)
print(DATA_CACHE_DIR)
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_CACHE_DIR / "documents-updates.jsonl"


def _extract_data():
    if not (DATA_CACHE_DIR / "inference_results").exists():
        subprocess.run(
            [
                "aws",
                "s3",
                "sync",
                "s3://cpr-prod-data-pipeline-cache/inference_results/latest/",
                str(DATA_CACHE_DIR / "inference_results"),
                "--exclude",
                "*",
                "--include",
                "*.json",
            ],
            check=True,
        )

    files = list((DATA_CACHE_DIR / "inference_results").glob("*.json"))
    return files


@flow(log_prints=True)
def materialize_vespa_updates_from_inference_results():
    print("Extracting data...")
    start = time.time()
    data = _extract_data()
    print(f"Extracted {len(data)} documents ({time.time() - start:.2f}s).")

    total = len(data)

    print(f"Writing {total} update_ops to {OUTPUT_FILE}...")
    start = time.time()
    with OUTPUT_FILE.open("wb") as f:
        for i, file in enumerate(data):
            # This is appended for translated documents
            document_id = file.stem.replace("_translated_en", "")

            with open(file, "rb") as inference_file:
                concepts = orjson.loads(inference_file.read())
                update_op = index(document_id, concepts)
                f.write(orjson.dumps(update_op) + b"\n")

                if i % 1000 == 0:
                    print(
                        f"Wrote {i}/{total} update_ops to {OUTPUT_FILE} ({time.time() - start:.2f}s)."
                    )

    print(f"Wrote {total} update_ops to {OUTPUT_FILE} ({time.time() - start:.2f}s).")

    print("Uploading to S3...")
    s3_client = boto3.client("s3")
    s3_client.upload_file(
        str(OUTPUT_FILE),
        "cpr-cache",
        "search/materialize_vespa_updates/from_inference_results.jsonl",
    )
    print("Uploaded to S3.")


if __name__ == "__main__":
    materialize_vespa_updates_from_inference_results()
