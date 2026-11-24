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


@flow(
    name="search-vespa-feeder-labels",
    description="Feed labels JSONL exported from fusion.published.vespa_labels into Vespa",
    timeout_seconds=RUN_TIMEOUT_SECONDS,
    task_runner=task_runner(max_workers=4),
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def labels_feeder_flow(
    batch_size: int = DEFAULT_BATCH_SIZE,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    s3_export_prefix: str | None = None,
) -> State | None:
    # Each row of the export is already a Vespa update operation
    # (`update`/`create`/`fields`), including the label -> label relationships, so
    # no deriver is needed. Exported by `fusion_run` in the data-lake repo.
    return vespa_feeder(
        s3_bucket="cpr-production-data-lake-fusion",
        s3_prefix="vespa/vespa_labels/",
        s3_export_prefix=s3_export_prefix,
        batch_size=batch_size,
        sample_rate=sample_rate,
    )
