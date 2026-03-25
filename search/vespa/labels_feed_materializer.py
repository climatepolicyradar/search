from pathlib import Path
from typing import TypedDict

import boto3
import orjson

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.inference_results import read as read_inference_results
from search.vespa.sources.wikibase import fetch_concepts_at_timestamps_sync

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_CACHE_DIR = REPO_ROOT_DIR / ".data_cache" / "vespa"
OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class VespaLabel(TypedDict):
    id: str
    type: str
    preferred_label: str
    alternative_labels: list[str]
    description: str
    negative_labels: list[str]


class VespaLabelUpdate(TypedDict):
    id: VespaAssign[str]
    type: VespaAssign[str]
    preferred_label: VespaAssign[str]
    alternative_labels: VespaAssign[list[str]]
    description: VespaAssign[str]
    negative_labels: VespaAssign[list[str]]


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
                "preferred_label": value["value"],
                "alternative_labels": [],
                "description": "",
                "negative_labels": [],
            }

    inference_results = read_inference_results()

    # Get wikibase IDs and timestamps
    wikibase_id_to_timestamps: dict[str, list[str]] = {}
    for _, inference_result in inference_results:
        for _, concepts in inference_result.items():
            for concept in concepts:
                wikibase_id_to_timestamps.setdefault(concept["id"], []).append(
                    concept["timestamp"]
                )

    # Use the most recent timestamp per concept
    wikibase_id_to_timestamp = {
        wid: max(timestamps) for wid, timestamps in wikibase_id_to_timestamps.items()
    }

    # Fetch full labels from Wikibase at each timestamp
    wikibase_concepts = fetch_concepts_at_timestamps_sync(wikibase_id_to_timestamp)

    if len(wikibase_concepts) < len(wikibase_id_to_timestamp):
        print("WARNING: fewer concepts returned from Wikibase than requested.")

    for concept in wikibase_concepts:
        identifier = f"concept::{concept['wikibase_id']}"
        labels[identifier] = {
            "id": identifier,
            "type": "concept",
            "preferred_label": concept["preferred_label"],
            "alternative_labels": concept["alternative_labels"],
            "description": concept["description"] or "",
            "negative_labels": concept["negative_labels"],
        }
    unique_labels = list(labels.values())

    print(f"Collected {len(unique_labels)} unique labels.")

    output_file = OUTPUT_CACHE_DIR / "labels_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for label in unique_labels:
            vespa_update: VespaUpdate[VespaLabelUpdate] = {
                "update": f"id:labels:labels::{label['id']}",
                "create": True,
                "fields": {
                    "id": {"assign": label["id"]},
                    "type": {"assign": label["type"]},
                    "preferred_label": {"assign": label["preferred_label"]},
                    "alternative_labels": {"assign": label["alternative_labels"]},
                    "description": {"assign": label["description"]},
                    "negative_labels": {"assign": label["negative_labels"]},
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
