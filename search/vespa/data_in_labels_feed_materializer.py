from pathlib import Path
from typing import TypedDict

import boto3
import orjson
from cpr_contracts import Label, LabelLabelRelationship

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api_labels import read as read_data_in_labels

REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_CACHE_DIR = REPO_ROOT_DIR / ".data_cache" / "vespa"
OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class VespaLabelLabelRelationship(TypedDict):
    id: str
    type: str
    value: str
    timestamp: int | None
    relationship: str | None


class VespaLabel(TypedDict):
    id: str
    type: str
    value: str
    alternative_labels: list[str]
    subconcept_labels: list[str]
    description: str
    negative_labels: list[str]
    label_source: str
    labels: list[VespaLabelLabelRelationship]


class VespaLabelUpdate(TypedDict):
    id: VespaAssign[str]
    type: VespaAssign[str]
    value: VespaAssign[str]
    alternative_labels: VespaAssign[list[str]]
    subconcept_labels: VespaAssign[list[str]]
    description: VespaAssign[str]
    negative_labels: VespaAssign[list[str]]
    label_source: VespaAssign[str]
    labels: VespaAssign[list[VespaLabelLabelRelationship]]


def _data_in_label_relationship_to_vespa_label_relationship(
    label_relationship: LabelLabelRelationship,
) -> VespaLabelLabelRelationship:
    """Transform and flatten `LabelLabelRelationship` to `VespaLabelLabelRelationship`."""
    value = label_relationship.value
    return {
        "id": value.id,
        "type": value.type,
        "value": value.value,
        "timestamp": (
            int(label_relationship.timestamp.timestamp())
            if label_relationship.timestamp is not None
            else None
        ),
        "relationship": label_relationship.type,
    }


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
            "labels": {"assign": label["labels"]},
        },
    }


def _data_in_label_to_vespa_label(label: Label) -> VespaLabel:
    vespa_label: VespaLabel = {
        "id": label.id,
        "type": label.type,
        "value": label.value,
        "alternative_labels": [],
        "subconcept_labels": [],
        "description": "",
        "negative_labels": [],
        "label_source": label.model_dump_json(),
        "labels": [
            _data_in_label_relationship_to_vespa_label_relationship(label_relationship)
            for label_relationship in label.labels
        ],
    }
    return vespa_label


def data_in_labels_feed_materializer():
    vespa_labels: list[VespaLabel] = [
        _data_in_label_to_vespa_label(label) for label in read_data_in_labels()
    ]

    vespa_label_updates: list[VespaUpdate[VespaLabelUpdate]] = [
        _vespa_label_to_vespa_update(vespa_label) for vespa_label in vespa_labels
    ]

    output_file = OUTPUT_CACHE_DIR / "data_in_labels_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for vespa_update in vespa_label_updates:
            f.write(orjson.dumps(vespa_update) + b"\n")

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/data_in_labels_feed_materializer.jsonl",
    )
    print(f"Uploaded {len(vespa_label_updates)} labels to S3.")

    return vespa_label_updates
