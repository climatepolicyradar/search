"""
Runs the daily Vespa feeds one at a time, in order.

documents and passages used to share a cron, and feeding both at once
saturates Vespa. This flow owns the schedule instead: it triggers each feed's
deployment and waits for it to finish before starting the next.

They are triggered as deployments rather than called as in-process subflows
because a subflow runs on its parent's infrastructure, and these feeds are
sized differently (passages asks for 4GB, documents 2GB). Triggering the
deployment keeps each feed on its own ECS task with its own sizing, and leaves
each one independently runnable - re-running a single feed by hand is the
escape hatch when one step of the chain fails.
"""

from typing import cast

from documents_flow import documents_feeder_flow
from labels_flow import labels_feeder_flow
from passages_flow import passages_feeder_flow
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from slack_notify import SlackNotify

from prefect import Flow, flow, get_run_logger, task

# Passages is the long pole at ~5h, so this is not a "should have finished by
# now" bound - it is a backstop against a child that wedges instead of failing.
# See the websocket note in flow.py's vespa_feeder for how a feed can sit in
# Running for days without ever reaching a terminal state.
_FEED_TIMEOUT_SECONDS = 6 * 60 * 60


class FeedRunFailed(Exception):
    """A feed deployment reached a state other than Completed."""


def _deployment_name(feed_flow: Flow) -> str:
    """
    Get a name that matches deployments.py

    deployments.py creates deployments with `name=flow.name`, leading to `{flow.name}/{flow.name}`
    """
    return f"{feed_flow.name}/{feed_flow.name}"


@task(task_run_name="feed-{name}")
def run_feed_deployment(
    name: str, timeout_seconds: int = _FEED_TIMEOUT_SECONDS
) -> FlowRun:
    """Trigger one feed's deployment and block until it reaches a terminal state."""
    run_logger = get_run_logger()
    run_logger.info(f"triggering {name}")

    # run_deployment return type is variant on sync | async
    # i.e. FlowRun | Coroutine[Any, Any, FlowRun]
    # This task is sync, so the cast narrows it to the FlowRun
    flow_run = cast(FlowRun, run_deployment(name=name, timeout=timeout_seconds))

    # run_deployment hands back the flow run whether it succeeded, failed, or
    # was still Running when the timeout expired. Left unchecked, a failed feed
    # would read as a completed step and the next feed would start on top of it.
    state = flow_run.state
    if state is None or not state.is_completed():
        raise FeedRunFailed(
            f"{name} finished as {state.name if state else 'unknown'} "
            f"(flow run {flow_run.id}). The chain stops here; re-run this feed's "
            "own deployment once the cause is fixed."
        )

    run_logger.info(f"{name} completed (flow run {flow_run.id})")
    return flow_run


@flow(
    name="search-vespa-feeder-daily",
    description="Run the documents, labels and passages feeds sequentially",
    log_prints=True,
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def nightly_feeder_flow() -> None:
    """
    Feed documents, then labels, then passages.

    Calling the task rather than submitting it blocks, so the order below is the
    order the feeds reach Vespa.

    No on_completion Slack hook: each feed notifies for itself, so the parent
    only speaks up when the chain as a whole goes wrong.
    """
    run_feed_deployment(name=_deployment_name(documents_feeder_flow))
    run_feed_deployment(name=_deployment_name(labels_feeder_flow))
    run_feed_deployment(name=_deployment_name(passages_feeder_flow))
