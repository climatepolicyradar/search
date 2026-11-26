from prefect.runtime import deployment, flow_run

from prefect import flow
from vespa_feeder.slack_notify import SlackNotify
from vespa_feeder.stream.metrics import MetricsSink
from vespa_feeder.stream.progress import parse_stats
from vespa_feeder.stream.s3 import S3Source
from vespa_feeder.stream.stream import RUN_TIMEOUT_SECONDS
from vespa_feeder.stream.vespa import VespaFeed, only_if_changed
from vespa_feeder.telemetry import force_flush, shutdown, tracer


def feed_labels(feed: VespaFeed, metrics: MetricsSink) -> None:
    """Feed the latest labels export into Vespa."""
    # Each row of the export is already a Vespa update operation
    # (`update`/`create`/`fields`), including the label -> label relationships,
    # so no transform is needed. Exported by `fusion_run` in the data-lake repo.
    source = S3Source(bucket="cpr-production-data-lake-fusion", prefix="vespa/vespa_labels/")
    updates = source.chain(only_if_changed)
    updates.chain(feed.feed).chain(parse_stats).run(metrics.drain)


@flow(
    name="search-vespa-feeder-labels",
    description="Feed labels JSONL exported from fusion.published.vespa_labels into Vespa",
    timeout_seconds=RUN_TIMEOUT_SECONDS,
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def labels_feeder_flow() -> None:
    try:
        with tracer.start_as_current_span("vespa_feeder"):
            feed = VespaFeed.create_from_ssm()
            metrics = MetricsSink(
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )
            feed_labels(feed=feed, metrics=metrics)
    finally:
        force_flush()
        shutdown()
