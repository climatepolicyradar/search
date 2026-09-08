from flow import feed_task_runner, vespa_feeder
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify

from prefect import flow


# max_workers bounds disk, Vespa connections and - critically - the number of
# task runs Prefect starts at once. See the submit loop in flow.py's
# vespa_feeder before changing it.
@flow(
    name="search-vespa-feeder-labels",
    description="Feed labels JSONL from S3 into Vespa",
    task_runner=feed_task_runner(max_workers=4),
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
