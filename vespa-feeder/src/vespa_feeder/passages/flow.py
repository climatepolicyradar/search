import re
from collections import Counter
from typing import Any, TypedDict

from prefect.runtime import deployment, flow_run

from prefect import flow
from vespa_feeder.passages.derived_data import (
    is_page_header_or_footer,
    looks_like_demoted_section,
    looks_like_reference_list,
    looks_like_short_heading,
    looks_like_table_of_contents,
)
from vespa_feeder.slack_notify import SlackNotify
from vespa_feeder.stream.metrics import MetricsSink
from vespa_feeder.stream.progress import parse_stats
from vespa_feeder.stream.s3 import S3Source
from vespa_feeder.stream.stream import RUN_TIMEOUT_SECONDS, skip_failures
from vespa_feeder.stream.vespa import VespaFeed
from vespa_feeder.telemetry import force_flush, shutdown, tracer

# `topic["value"]`` arrives as a classifier's repr, e.g. `BertBasedClassifier("procedural` justice")`
# The classifier name varies, but the label text is always the sole quoted argument.
# TODO: This is gnarly and should be fixed upstream
_CLASSIFIER_VALUE_RE = re.compile(r'^\w+\("(.*)"\)$')

_SECTION_CONTEXT_PREFIX = "Section context: this excerpt is from the section titled '"
_SECTION_CONTEXT_SUFFIX = "'. "


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


def passage_update(record: dict[str, Any]) -> dict[str, Any]:
    """Apply all passages derivers to a record, in sequence."""
    record = _derive_labels_from_topics(record)
    record = _derive_document_ref(record)
    record = _derive_heading_text(record)
    record = _derive_passage_type_flags(record)
    return record


def _parse_classifier_value(value: str) -> str:
    match = _CLASSIFIER_VALUE_RE.match(value)
    return match.group(1) if match else value


def _derive_labels_from_topics(record: dict[str, Any]) -> dict[str, Any]:
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


def _derive_document_ref(record: dict[str, Any]) -> dict[str, Any]:
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


def _derive_heading_text(record: dict[str, Any]) -> dict[str, Any]:
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


def _derive_passage_type_flags(record: dict[str, Any]) -> dict[str, Any]:
    """
    Set the `looks_like_*` bools and `is_page_header_or_footer`.

    Derived from the record's own text, pages and content type. The Snowflake
    export doesn't carry them, so without this the fields default
    false and the penalties they drive in passages.sd's `nativerank` profile are
    inert. `pages` is absent for passages with no page data (HTML documents), in
    which case `looks_like_table_of_contents` skips its front-matter page veto.
    """
    fields = record.get("fields", {})
    content = fields.get("content", {}).get("assign", "")
    content_type = fields.get("content_type", {}).get("assign", "")
    heading_text = fields.get("heading_text", {}).get("assign", "")
    pages = fields.get("pages", {}).get("assign") or []
    page_numbers = [page["number"] for page in pages]

    fields["looks_like_short_heading"] = {
        "assign": looks_like_short_heading(content, content_type)
    }
    fields["looks_like_table_of_contents"] = {
        "assign": looks_like_table_of_contents(content, page_numbers)
    }
    fields["looks_like_reference_list"] = {
        "assign": looks_like_reference_list(content, content_type)
    }
    fields["is_page_header_or_footer"] = {
        "assign": is_page_header_or_footer(content_type)
    }
    fields["looks_like_demoted_section"] = {
        "assign": looks_like_demoted_section(heading_text, content, content_type)
    }
    return record


def feed_passages(feed: VespaFeed, metrics: MetricsSink) -> None:
    """Feed the latest passages export into Vespa."""
    source = S3Source(
        bucket="cpr-prod-snowflake-data-export",
        prefix="production/published/pipeline_data_in_vespa_passage_updates_v1/",
    )
    updates = source.chain(skip_failures(passage_update))
    updates.chain(feed.feed).chain(parse_stats).run(metrics.drain)


@flow(
    name="search-vespa-feeder-passages",
    description="Feed passages JSONL from the data-lake Snowflake export into Vespa, deriving document_ref per record",
    timeout_seconds=RUN_TIMEOUT_SECONDS,
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def passages_feeder_flow() -> None:
    try:
        with tracer.start_as_current_span("vespa_feeder"):
            feed = VespaFeed.create_from_ssm()
            metrics = MetricsSink(
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )
            feed_passages(feed=feed, metrics=metrics)
    finally:
        force_flush()
        shutdown()
