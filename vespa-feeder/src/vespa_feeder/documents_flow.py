from typing import Any

from prefect.client.schemas.objects import State

from prefect import flow
from vespa_feeder.feeder import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_SAMPLE_RATE,
    RUN_TIMEOUT_SECONDS,
    vespa_feeder,
)
from vespa_feeder.slack_notify import SlackNotify
from vespa_feeder.task_runner import task_runner


def derive_fusion_document_data(row: dict[str, Any]) -> dict[str, Any]:
    """
    Turn a `fusion.published.vespa_documents` row into a Vespa update.

    A Fusion row is one flat object keyed by the Vespa field names, unlike the
    legacy export whose rows are already `{update, create, fields}`. Fusion
    owns every value, including the derived ones (`principal_id`,
    `collection_id`, the hoisted attributes, `attributes_created_at` and
    `distinct_concept_ids`), so each column is assigned as-is to the field of
    the same name. The one exception is `version`, which is always null
    upstream and not fed.
    """
    document_id = row.get("id")
    if not document_id:
        raise ValueError(f"Fusion document row has no id: columns={sorted(row)}")

    return {
        "update": f"id:documents:documents::{document_id}",
        "create": True,
        "fields": {
            column: {"assign": value}
            for column, value in row.items()
            if column != "version"
        },
    }


# max_workers bounds disk, Vespa connections and - critically - the number of
# task runs Prefect starts at once. See the submit loop in vespa_feeder
# before changing it.
@flow(
    name="search-vespa-feeder-documents",
    description="Feed documents JSONL exported from fusion.published.vespa_documents into Vespa",
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
    # Exported by `fusion_run` in the data-lake repo.
    return vespa_feeder(
        s3_bucket="cpr-production-data-lake-fusion",
        s3_prefix="vespa/vespa_documents/",
        s3_export_prefix=s3_export_prefix,
        derive_data_from_source=derive_fusion_document_data,
        batch_size=batch_size,
        sample_rate=sample_rate,
    )
