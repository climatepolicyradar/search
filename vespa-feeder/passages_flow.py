import re
from collections import Counter
from typing import TypedDict

from flow import vespa_feeder
from passages_derived_data import (
    looks_like_reference_list,
    looks_like_short_heading,
    looks_like_table_of_contents,
)
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
    """
    Set `labels` and `concept_counts` on a passages update record from its `topics`.

    They are coupled as the derived value for `concept_counts` depends on the derived `labels`.
    """
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
    record["fields"]["concept_counts"] = {
        "assign": dict(Counter(label["id"] for label in labels))
    }
    record["fields"].pop("topics", None)
    return record


def derive_passage_type_flags(record: dict) -> dict:
    """
    Set the three `looks_like_*` bools, derived from the record's own text and pages.

    The Snowflake export doesn't carry them, so without this the fields default
    false and the penalties they drive in passages.sd's `nativerank` profile are
    inert. `pages` is absent for passages with no page data (HTML documents), in
    which case `looks_like_table_of_contents` skips its front-matter page veto.
    """
    fields = record.get("fields", {})
    content = fields.get("content", {}).get("assign", "")
    pages = fields.get("pages", {}).get("assign") or []
    page_numbers = [page["number"] for page in pages]
    content_type = fields.get("content_type", {}).get("assign", "")

    fields["looks_like_short_heading"] = {"assign": looks_like_short_heading(content)}
    fields["looks_like_table_of_contents"] = {
        "assign": looks_like_table_of_contents(content, page_numbers)
    }
    fields["looks_like_reference_list"] = {
        "assign": looks_like_reference_list(content, content_type)
    }
    return record


def derive_passage_data(record: dict) -> dict:
    """Apply all passages derivers to a record, in sequence."""
    record = derive_labels_from_topics(record)
    record = derive_document_ref(record)
    record = derive_heading_text(record)
    record = derive_passage_type_flags(record)
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


_SECTION_CONTEXT_PREFIX = "Section context: this excerpt is from the section titled '"
_SECTION_CONTEXT_SUFFIX = "'. "


def derive_heading_text(record: dict) -> dict:
    """
    Set `heading_text` on a passages update record, parsed out of `serialised_text`.

    The snowflake export has no `heading_text` column, only `heading_id`, so this uses
    `serialised_text`: "Section context: ... titled '<HEADING>'. <content>".

    Left untouched unless the record carries that whole shape - the prefix, and a
    `content` that is exactly the tail of `serialised_text`. A partial update without
    `content`, a null, or a whitespace mismatch is skipped; a bad parse would index a
    full passage body as `heading_text` and overwrite the stored value.
    """
    fields = record.get("fields", {})
    serialised_text = fields.get("serialised_text", {}).get("assign") or ""
    if not serialised_text.startswith(_SECTION_CONTEXT_PREFIX):
        return record

    content = fields.get("content", {}).get("assign") or ""
    if not content or not serialised_text.endswith(content):
        return record

    heading = serialised_text[len(_SECTION_CONTEXT_PREFIX) : -len(content)]
    if not heading.endswith(_SECTION_CONTEXT_SUFFIX):
        return record

    heading = heading.removesuffix(_SECTION_CONTEXT_SUFFIX).strip()
    if heading:
        fields["heading_text"] = {"assign": heading}
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
        derive_data_from_source=derive_passage_data,
        max_concurrent_downloads=8,
    )
