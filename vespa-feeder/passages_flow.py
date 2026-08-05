from flow import vespa_feeder
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify

from prefect import flow


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
