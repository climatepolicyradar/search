import logging
import os
import textwrap

from prefect.client.schemas.objects import FlowRun, State
from prefect.flows import Flow
from prefect.runtime import deployment
from prefect.settings import PREFECT_UI_URL
from prefect_slack.credentials import SlackCredentials
from telemetry import feeder_metrics, force_flush, get_feed_stats

logger = logging.getLogger(__name__)


class SlackNotify:
    SLACK_BLOCK = "slack-navigator-notifier-bot"
    CHANNEL = "prod-updates"
    FLOW_RUN_URL = "{base_url}/flow-runs/flow-run/{run_id}"
    # Pre-filtered to the deployment; the dashboard has no `run_name`
    # variable, so its Runs table does the rest.
    GRAFANA_URL = (
        "https://climatepolicyradar.grafana.net/d/vespa-feeder-flows"
        "?var-deployment_name={deployment_name}&from=now-24h&to=now"
    )

    @classmethod
    def _get_environment(cls) -> str:
        return os.getenv("AWS_ENV", "sandbox")

    @classmethod
    def _format_feed_stats(cls, crashed: bool = False) -> str:
        """
        The "Records fed" field, which a crash cannot fill in.

        A crash kills the flow process before it sets the stats, and this
        hook runs in a different process, so the dict is empty either way.
        Printing `—` read as "zero records fed" rather than "unknown".
        """
        stats = get_feed_stats()
        if crashed and not stats:
            grafana_url = cls.GRAFANA_URL.format(deployment_name=deployment.name)
            return (
                "*Records fed*\n`unknown — run crashed`\n"
                f"<{grafana_url}|View progress in Grafana>"
            )
        if not stats:
            return "*Records fed*\n`—`"
        return f"*Records fed*\n`in={stats['input']} ok={stats['ok']} err={stats['errors']}`"

    @classmethod
    def _build_blocks(
        cls,
        flow: Flow,
        flow_run: FlowRun,
        state: State,
        ui_url: str,
        crashed: bool = False,
    ) -> list:
        icon = "✅" if state.is_completed() else "❌"
        header = f"{icon} Flow run *{flow.name}/{deployment.name}/{flow_run.name}* `{state.name}`"
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": header},
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View in Prefect",
                        "emoji": True,
                    },
                    "value": "view_in_prefect",
                    "url": ui_url,
                    "action_id": "button-action",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Environment*\n`{cls._get_environment()}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": cls._format_feed_stats(crashed=crashed),
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Version*\n`{flow_run.deployment_version}`",
                    },
                    {"type": "mrkdwn", "text": f"*Timestamp*\n`{state.timestamp}`"},
                ],
            },
        ]
        if state.message:
            state_message = textwrap.shorten(
                state.message, width=3000, placeholder="..."
            )
            blocks += [
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*State message:*\n\n>{state_message}",
                    },
                },
            ]
        return blocks

    @classmethod
    async def _send(
        cls, flow: Flow, flow_run: FlowRun, state: State, crashed: bool = False
    ) -> None:
        if cls._get_environment() != "prod":
            return

        ui_url = cls.FLOW_RUN_URL.format(
            base_url=PREFECT_UI_URL.value(), run_id=flow_run.id
        )
        icon = "✅" if state.is_completed() else "❌"
        text = (
            f"{icon} Flow run <{ui_url}|{flow.name}/{deployment.name}/{flow_run.name}> "
            f"state `{state.name}` at {state.timestamp}"
        )
        credentials = await SlackCredentials.aload(cls.SLACK_BLOCK)
        client = credentials.get_client()
        await client.chat_postMessage(
            channel=cls.CHANNEL,
            text=text,
            blocks=cls._build_blocks(flow, flow_run, state, ui_url, crashed=crashed),
        )

    @classmethod
    async def on_success(cls, flow: Flow, flow_run: FlowRun, state: State) -> None:
        """Logic for updating Slack on Prefect flow success"""
        await cls._send(flow, flow_run, state)

    @classmethod
    async def on_failure(cls, flow: Flow, flow_run: FlowRun, state: State) -> None:
        """Logic for updating Slack on Prefect flow failure"""
        await cls._send(flow, flow_run, state)

    @classmethod
    async def on_crashed(cls, flow: Flow, flow_run: FlowRun, state: State) -> None:
        """
        Record the crash and notify Slack on a Prefect flow crash (e.g. OOM/SIGKILL).

        This hook's process is the only one still alive after a crash, so it
        is the only place the run can be reported from. It exits as soon as
        the hook returns, hence the explicit flush.
        """
        try:
            feeder_metrics.record_run_crashed(
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )
            force_flush()
        except Exception:
            logger.exception("Failed to record the crash metric")

        await cls._send(flow, flow_run, state, crashed=True)

    @classmethod
    async def on_cancellation(cls, flow: Flow, flow_run: FlowRun, state: State) -> None:
        """Logic for updating Slack on Prefect flow cancellation"""
        await cls._send(flow, flow_run, state)
