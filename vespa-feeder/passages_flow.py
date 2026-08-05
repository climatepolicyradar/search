import re
from typing import TypedDict

from flow import vespa_feeder
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify

from prefect import flow

# `topic["value"]`` arrives as a classifier's repr, e.g. `BertBasedClassifier("procedural` justice")`
# The classifier name varies, but the label text is always the sole quoted argument.
# TODO: This is gnarly and should be fixed upstream
_CLASSIFIER_VALUE_RE = re.compile(r'^\w+\("(.*)"\)$')


def _parse_classifier_value(value: str) -> str:
    match = _CLASSIFIER_VALUE_RE.match(value)
    return match.group(1) if match else value


class DataLakeTopic(TypedDict):
    classifier_id: str
    concept_id: str
    end_index: int
    id: str
    labelled_text: str
    labellers: list[str]
    prediction_probability: float
    start_index: int
    timestamps: list[str]
    value: str


class VespaPassageLabel(TypedDict):
    # These are the core Label fields i.e. the node
    id: str
    type: str
    value: str
    # These are fields that related the label to the passage i.e. the edge
    classifier_id: str
    end_index: int
    labelled_text: str
    labellers: list[str]
    prediction_probability: float
    start_index: int
    timestamps: list[str]


def derive_labels_from_topics(record: dict) -> dict:
    """Set `labels` on a passages update record, derived from its own `topic` field."""
    topics: list[DataLakeTopic] = (
        record.get("fields", {}).get("topics", {}).get("assign", [])
    )

    labels: list[VespaPassageLabel] = [
        {
            "id": f"concept::{topic['concept_id']}",
            "type": "concept",
            "value": _parse_classifier_value(topic["labellers"][0]),
            "classifier_id": topic["classifier_id"],
            "end_index": topic["end_index"],
            "labelled_text": topic["labelled_text"],
            "labellers": topic["labellers"],
            "prediction_probability": topic["prediction_probability"],
            "start_index": topic["start_index"],
            "timestamps": topic["timestamps"],
        }
        for topic in topics
    ]

    record["fields"]["labels"] = {"assign": labels}
    record["fields"].pop("topics", None)
    return record


def derive_document_ref(record: dict) -> dict:
    """
    Set `document_ref` on a passages update record, manufactured from its own `document_id`.

    Pure string formatting, no lookup - once this resolves, `principal_id`
    (imported in passages.sd via `import field document_ref.principal_id`)
    follows automatically at query time, with no passage-side work needed for it.
    """
    document_id = record.get("fields", {}).get("document_id", {}).get("assign")
    if document_id is None:
        return record

    record["fields"]["document_ref"] = {
        "assign": f"id:documents:documents::{document_id}"
    }
    return record


@flow(
    name="search-vespa-feeder-passages",
    description="Feed passages JSONL from the data-lake Snowflake export into Vespa, deriving document_ref per record",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def passages_feeder_flow() -> State | None:
    # Data-lake export files are ~100x smaller than the old materializer's -
    # see flow.py's _DEFAULT_MAX_CONCURRENT_DOWNLOADS for why 8 is safe here.
    return vespa_feeder(
        s3_bucket="cpr-prod-snowflake-data-export",
        s3_key="production/published/pipeline_data_in_vespa_passage_updates_v1/latest",
        derive_data_from_source=derive_document_ref,
        max_concurrent_downloads=8,
    )
