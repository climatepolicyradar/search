from typing import Any

import orjson
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify
from task_runner import task_runner
from vespa_feeder import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_SAMPLE_RATE,
    RUN_TIMEOUT_SECONDS,
    vespa_feeder,
)

from prefect import flow


def _is_principal(document_source: dict[str, Any]) -> bool:
    return any(
        label.get("value", {}).get("id") == "status::Principal"
        for label in document_source.get("labels", [])
    )


def _principal_id_from_document_source(document_source: dict[str, Any]) -> str | None:
    """
    Mirror of `_derive_principal_id` in `search/vespa/documents_feed_materializer.py`.

    Operates on the JSON-decoded `document_source` (the original cpr_contracts.Document,
    already embedded verbatim in every documents update record) rather than a
    `Document` model instance - vespa-feeder has no dependency on cpr_contracts.
    """
    if _is_principal(document_source):
        return document_source.get("id")

    matches = [
        relationship
        for relationship in document_source.get("documents", [])
        if relationship.get("type") in {"member_of", "is_version_of"}
    ]
    if not matches:
        return None
    return matches[0].get("value", {}).get("id")


def _collection_id_from_document_source(document_source: dict[str, Any]) -> str | None:
    if not _is_principal(document_source):
        return None

    matches = [
        relationship
        for relationship in document_source.get("documents", [])
        if relationship.get("type") == "member_of"
    ]

    if not matches:
        return None

    return matches[0].get("value", {}).get("id")


def _document_source(record: dict[str, Any]) -> dict[str, Any] | None:
    raw: str | None = record.get("fields", {}).get("document_source", {}).get("assign")
    if raw is None:
        return None
    return orjson.loads(raw)


def derive_id_if_missing(
    record: dict[str, Any],
    document_source: dict[str, Any],
) -> dict[str, Any]:
    """
    Use the `id` from the vespa update, or, if that is missing use the `id` from the `document_source` field.

    This is a temporary workaround while we wait for an upstream feed change
    @see: https://github.com/climatepolicyradar/data-lake/pull/539
    TODO: https://linear.app/climate-policy-radar/issue/FUS-440/remove-derive-id-if-missing-from-documents-flow
    """
    if "id" in record.get("fields", {}):
        return record

    document_id = document_source.get("id")
    if document_id is not None:
        record["fields"]["id"] = {"assign": document_id}
    return record


def derive_distinct_concept_ids(record: dict[str, Any]) -> dict[str, Any]:
    """Set `distinct_concept_ids` from the keys of the record's own `concept_counts`, so concepts can be grouped."""
    concept_counts = record.get("fields", {}).get("concept_counts", {}).get("assign")

    if concept_counts is None:
        return record

    record["fields"]["distinct_concept_ids"] = {"assign": sorted(concept_counts)}

    return record


def derive_document_data(record: dict[str, Any]) -> dict[str, Any]:
    """Apply all passages derivers to a record, in sequence."""
    if (document_source := _document_source(record)) is not None:
        record = derive_principal_id(record, document_source)
        record = derive_collection_id(record, document_source)
        record = derive_id_if_missing(record, document_source)
    record = derive_hoisted_attributes(record)
    record = derive_distinct_concept_ids(record)

    return record


# Hoisted so they can be served from memory: `attributes_string` is in no document
# summary, so a value inside it is otherwise only reachable by grouping.
_HOISTED_ATTRIBUTE_KEYS: tuple[str, ...] = ("deprecated_slug", "last_updated_date")


def derive_hoisted_attributes(record: dict[str, Any]) -> dict[str, Any]:
    """Set `deprecated_slug` and `last_updated_date` from the record's own `attributes_string`."""
    attributes = record.get("fields", {}).get("attributes_string", {}).get("assign")

    if attributes is None:
        return record

    for key in _HOISTED_ATTRIBUTE_KEYS:
        record["fields"][key] = {"assign": attributes.get(key, "")}

    return record


def derive_principal_id(
    record: dict[str, Any],
    document_source: dict[str, Any],
) -> dict[str, Any]:
    """Set `principal_id` on a documents update record, derived from its own `document_source`."""
    principal_id = _principal_id_from_document_source(document_source)
    if principal_id is not None:
        record["fields"]["principal_id"] = {"assign": principal_id}
    return record


def derive_collection_id(
    record: dict[str, Any],
    document_source: dict[str, Any],
) -> dict[str, Any]:
    """Set `collection_id` on a documents update record, derived from its own `document_source`."""
    collection_id = _collection_id_from_document_source(document_source)
    record["fields"]["collection_id"] = {"assign": collection_id or ""}
    return record


# max_workers bounds disk, Vespa connections and - critically - the number of
# task runs Prefect starts at once. See the submit loop in vespa_feeder
# before changing it.
@flow(
    name="search-vespa-feeder-documents",
    description="Feed documents JSONL from S3 into Vespa, deriving fields per record",
    # Paired with the drain's own budget - see RUN_TIMEOUT_SECONDS.
    timeout_seconds=RUN_TIMEOUT_SECONDS,
    task_runner=task_runner(max_workers=4),
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def documents_feeder_flow(
    batch_size: int = DEFAULT_BATCH_SIZE,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    s3_export_prefix: str | None = None,
) -> State | None:
    bucket = "cpr-prod-snowflake-data-export"
    prefix = "production/published/pipeline_data_in_vespa_documents_updates_v1/"
    return vespa_feeder(
        s3_bucket=bucket,
        s3_prefix=prefix,
        s3_export_prefix=s3_export_prefix,
        derive_data_from_source=derive_document_data,
        batch_size=batch_size,
        sample_rate=sample_rate,
    )
