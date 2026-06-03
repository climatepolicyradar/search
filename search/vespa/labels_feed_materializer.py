from pathlib import Path
from typing import TypedDict

import boto3
import orjson
from cpr_contracts import Label, LabelRelationship

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.inference_results import read as read_inference_results
from search.vespa.sources.wikibase import (
    WikibaseConcept,
    fetch_concepts_at_timestamps_sync,
)

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_CACHE_DIR = REPO_ROOT_DIR / ".data_cache" / "vespa"
OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class VespaLabel(TypedDict):
    id: str
    type: str
    value: str
    alternative_labels: list[str]
    subconcept_labels: list[str]
    description: str
    negative_labels: list[str]
    label_source: str


class VespaLabelUpdate(TypedDict):
    id: VespaAssign[str]
    type: VespaAssign[str]
    value: VespaAssign[str]
    alternative_labels: VespaAssign[list[str]]
    subconcept_labels: VespaAssign[list[str]]
    description: VespaAssign[str]
    negative_labels: VespaAssign[list[str]]
    label_source: VespaAssign[str]


def _vespa_label_to_vespa_update(label: VespaLabel) -> VespaUpdate[VespaLabelUpdate]:
    """Convert a Vespa label to a Vespa update operation."""
    return {
        "update": f"id:labels:labels::{label['id']}",
        "create": True,
        "fields": {
            "id": {"assign": label["id"]},
            "type": {"assign": label["type"]},
            "value": {"assign": label["value"]},
            "alternative_labels": {"assign": label["alternative_labels"]},
            "subconcept_labels": {"assign": label["subconcept_labels"]},
            "description": {"assign": label["description"]},
            "negative_labels": {"assign": label["negative_labels"]},
            "label_source": {"assign": label["label_source"]},
        },
    }


def _source_label_relationship_to_vespa_label(
    label_rel: LabelRelationship,
) -> VespaLabel:
    """
    Convert a document's label relationship into a ``VespaLabel`` row.

    ``label_source`` must be the flat label (``id``/``type``/``value``) so the
    labels search engine can parse it as :class:`DataInLabel`. Storing the
    relationship envelope here silently drops every document-derived label at
    read time.
    """
    value = label_rel.value
    vespa_label: VespaLabel = {
        "id": value.id,
        "type": value.type,
        "value": value.value,
        "alternative_labels": [],
        "subconcept_labels": [],
        "description": "",
        "negative_labels": [],
        "label_source": value.model_dump_json(),
    }
    return vespa_label


def _wikibase_concept_to_vespa_label(concept: WikibaseConcept) -> VespaLabel:
    """Convert a Wikibase concept into a ``VespaLabel`` row."""
    identifier = f"concept::{concept['wikibase_id']}"
    source_label= Label(
        id=identifier,
        type="concept",
        value=concept["preferred_label"],
        labels = []
    )
    vespa_label: VespaLabel = {
        "id": identifier,
        "type": "concept",
        "value": concept["preferred_label"],
        "alternative_labels": concept["alternative_labels"],
        "subconcept_labels": concept["subconcept_labels"],
        "description": concept["description"] or "",
        "negative_labels": concept["negative_labels"],
        "label_source": source_label.model_dump_json(),
    }
    return vespa_label


def labels_feed_materializer():
    labels: dict[str, VespaLabel] = {}

    documents = read_documents()
    for document in documents:
        for label_rel in document.labels or []:
            vespa_label = _source_label_relationship_to_vespa_label(label_rel)
            labels[vespa_label["id"]] = vespa_label

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
        vespa_label = _wikibase_concept_to_vespa_label(concept)
        labels[vespa_label["id"]] = vespa_label

    unique_labels = list(labels.values())

    print(f"Collected {len(unique_labels)} unique labels.")

    output_file = OUTPUT_CACHE_DIR / "labels_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for label in unique_labels:
            vespa_update: VespaUpdate[VespaLabelUpdate] = _vespa_label_to_vespa_update(
                label
            )
            f.write(orjson.dumps(vespa_update) + b"\n")

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/labels_feed_materializer.jsonl",
    )
    print(f"Uploaded {len(labels)} labels to S3.")


if __name__ == "__main__":
    labels_feed_materializer()
