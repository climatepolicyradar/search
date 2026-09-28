from vespa_feeder import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_SAMPLE_RATE,
    vespa_feeder,
)
from slack_notify import SlackNotify
from task_runner import task_runner

from prefect import flow


@flow(
    name="search-vespa-feeder-labels",
    description="Feed labels JSONL from S3 into Vespa",
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
) -> None:
    # @related: LABEL_RELATIONSHIPS_DO_NOT_EXIST
    # We do not get the label --> label relationships from Snowflake.
    # We have an interim solution of having our own materializer until that
    # work has been done upstream.
    # @see: https://app.notion.com/p/climatepolicyradar/RFC-Label-relationships-Tech-Debt-Mandate-3c79109609a48031bb45c50e01b9735c?source=copy_link
    vespa_feeder(
        s3_bucket="cpr-cache",
        s3_key="search/vespa/labels_feed_materializer.jsonl",
        batch_size=batch_size,
        sample_rate=sample_rate,
    )
