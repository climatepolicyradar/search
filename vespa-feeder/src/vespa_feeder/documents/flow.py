from typing import Any

from prefect.runtime import deployment, flow_run

from prefect import flow
from vespa_feeder.slack_notify import SlackNotify
from vespa_feeder.stream.metrics import MetricsSink
from vespa_feeder.stream.progress import parse_stats
from vespa_feeder.stream.s3 import S3Source
from vespa_feeder.stream.stream import RUN_TIMEOUT_SECONDS, skip_failures
from vespa_feeder.stream.vespa import VespaFeed
from vespa_feeder.telemetry import force_flush, shutdown, tracer


def document_update(row: dict[str, Any]) -> dict[str, Any]:
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


def feed_documents(feed: VespaFeed, metrics: MetricsSink) -> None:
    """Feed the latest documents export into Vespa."""
    # Exported by `fusion_run` in the data-lake repo.
    source = S3Source(bucket="cpr-production-data-lake-fusion", prefix="vespa/vespa_documents/")
    updates = source.chain(skip_failures(document_update))
    updates.chain(feed.feed).chain(parse_stats).run(metrics.drain)


@flow(
    name="search-vespa-feeder-documents",
    description="Feed documents JSONL exported from fusion.published.vespa_documents into Vespa",
    timeout_seconds=RUN_TIMEOUT_SECONDS,
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def documents_feeder_flow() -> None:
    try:
        with tracer.start_as_current_span("vespa_feeder"):
            feed = VespaFeed.create_from_ssm()
            metrics = MetricsSink(
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )
            feed_documents(feed=feed, metrics=metrics)
    finally:
        force_flush()
        shutdown()
