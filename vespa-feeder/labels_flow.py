from flow import vespa_feeder
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify

from prefect import flow


@flow(
    name="search-vespa-feeder-labels",
    description="Feed labels JSONL from S3 into Vespa",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def labels_feeder_flow() -> State | None:
    return vespa_feeder(
        s3_bucket="cpr-cache", s3_key="search/vespa/labels_feed_materializer.jsonl"
    )


# TODO: this is temporary - https://linear.app/climate-policy-radar/issue/FUS-238/remove-temporary-data-in-pipelines-labels-vespa-materializer-and
@flow(
    name="search-vespa-feeder-data-in-labels",
    description="Feed data in labels JSONL from S3 into Vespa",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def data_in_labels_feeder_flow() -> State | None:
    return vespa_feeder(
        s3_bucket="cpr-cache",
        s3_key="search/vespa/data_in_labels_feed_materializer.jsonl",
    )
