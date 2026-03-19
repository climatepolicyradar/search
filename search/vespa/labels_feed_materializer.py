from pathlib import Path
from typing import TypedDict

import boto3
import orjson

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.inference_results import read as read_inference_results

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_CACHE_DIR = REPO_ROOT_DIR / ".data_cache" / "vespa"
OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class VespaLabel(TypedDict):
    id: str
    type: str
    value: str


class VespaLabelUpdate(TypedDict):
    id: VespaAssign[str]
    type: VespaAssign[str]
    value: VespaAssign[str]


def labels_feed_materializer():
    labels: dict[str, VespaLabel] = {}

    documents = read_documents()
    for document in documents:
        for label_rel in document.get("labels") or []:
            value = label_rel["value"]
            identifier = f"{value['type']}::{value['id']}"
            labels[identifier] = {
                "id": identifier,
                "type": value["type"],
                "value": value["value"],
            }

    inference_results = read_inference_results()
    for document_id, inference_result in inference_results:
        for passage_id, concepts in inference_result.items():
            for concept in concepts:
                identifier = f"concept::{concept['name']}"
                labels[identifier] = {
                    "id": identifier,
                    "type": "concept",
                    "value": concept["name"],
                }

    unique_labels = list(labels.values())

    print(f"Collected {len(unique_labels)} unique labels.")

    output_file = OUTPUT_CACHE_DIR / "labels_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for label in unique_labels:
            vespa_update: VespaUpdate[VespaLabelUpdate] = {
                "update": f"id:labels:labels::{label.get('id')}",
                "create": True,
                "fields": {
                    "id": {"assign": label["id"]},
                    "value": {"assign": label["value"]},
                    "type": {"assign": label["type"]},
                },
            }
            f.write(orjson.dumps(vespa_update) + b"\n")

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/labels_feed_materializer.jsonl",
    )
    print(f"Uploaded {len(labels)} labels to S3.")


if __name__ == "__main__":
    labels_feed_materializer()
