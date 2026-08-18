import orjson
from flow import vespa_feeder
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify

from prefect import flow

_CONCEPTS_FEED_TIMEOUT_SECONDS = 7200


def _principal_id_from_document_source(document_source: dict) -> str | None:
    """
    Mirror of `_derive_principal_id` in `search/vespa/documents_feed_materializer.py`.

    Operates on the JSON-decoded `document_source` (the original cpr_contracts.Document,
    already embedded verbatim in every documents update record) rather than a
    `Document` model instance - vespa-feeder has no dependency on cpr_contracts.
    """
    is_principal = any(
        label.get("value", {}).get("id") == "status::Principal"
        for label in document_source.get("labels", [])
    )
    if is_principal:
        return document_source.get("id")

    matches = [
        rel
        for rel in document_source.get("documents", [])
        if rel.get("type") in {"member_of", "is_version_of"}
    ]
    if not matches:
        return None
    return matches[0].get("value", {}).get("id")


def derive_principal_id(record: dict) -> dict:
    """Set `principal_id` on a documents update record, derived from its own `document_source`."""
    document_source_raw = (
        record.get("fields", {}).get("document_source", {}).get("assign")
    )
    if document_source_raw is None:
        return record

    principal_id = _principal_id_from_document_source(orjson.loads(document_source_raw))
    if principal_id is not None:
        record["fields"]["principal_id"] = {"assign": principal_id}
    return record


@flow(
    name="search-vespa-feeder-documents",
    description="Feed documents JSONL from S3 into Vespa, deriving principal_id per record",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def documents_feeder_flow() -> State | None:
    return vespa_feeder(
        s3_bucket="cpr-prod-snowflake-data-export",
        s3_key="production/published/pipeline_data_in_vespa_documents_updates_v1/latest",
        derive_data_from_source=derive_principal_id,
    )


@flow(
    name="search-vespa-feeder-documents-concepts",
    description="Feed documents concepts JSONL from S3 into Vespa",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def documents_concepts_feeder_flow() -> State | None:
    return vespa_feeder(
        s3_bucket="cpr-cache",
        s3_key="search/vespa/documents_concepts_feed_materializer.jsonl",
        feed_timeout_seconds=_CONCEPTS_FEED_TIMEOUT_SECONDS,
    )


@flow(
    name="search-vespa-feeder-documents-principal-concepts",
    description="Feed documents principal concepts JSONL from S3 into Vespa",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def documents_principal_concepts_feeder_flow() -> State | None:
    return vespa_feeder(
        s3_bucket="cpr-cache",
        s3_key="search/vespa/documents_principal_concepts_feed_materializer.jsonl",
        feed_timeout_seconds=_CONCEPTS_FEED_TIMEOUT_SECONDS,
    )
