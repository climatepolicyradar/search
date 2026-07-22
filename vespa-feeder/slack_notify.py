import os
import textwrap

from prefect.client.schemas.objects import FlowRun, State
from prefect.flows import Flow
from prefect.runtime import deployment
from prefect.settings import PREFECT_UI_URL
from prefect_slack.credentials import SlackCredentials
from telemetry import get_feed_stats


class SlackNotify:
    SLACK_BLOCK = "slack-navigator-notifier-bot"
    CHANNEL = "prod-updates"
    FLOW_RUN_URL = "{base_url}/flow-runs/flow-run/{run_id}"

    @classmethod
    def _get_environment(cls) -> str:
        return os.getenv("AWS_ENV", "sandbox")

    @staticmethod
    def _format_feed_stats() -> str:
        stats = get_feed_stats()
        if not stats:
            return "*Records fed*\n`—`"
        return f"*Records fed*\n`in={stats['input']} ok={stats['ok']} err={stats['errors']}`"

    @classmethod
    def _build_blocks(
        cls, flow: Flow, flow_run: FlowRun, state: State, ui_url: str
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
                        "text": cls._format_feed_stats(),
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
    async def _send(cls, flow: Flow, flow_run: FlowRun, state: State) -> None:
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
        credentials = SlackCredentials.load(cls.SLACK_BLOCK)
        client = credentials.get_client()  # type: ignore
        await client.chat_postMessage(
            channel=cls.CHANNEL,
            text=text,
            blocks=cls._build_blocks(flow, flow_run, state, ui_url),
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
        """Logic for updating Slack on Prefect flow crash (e.g. OOM/SIGKILL)"""
        await cls._send(flow, flow_run, state)

    @classmethod
    async def on_cancellation(cls, flow: Flow, flow_run: FlowRun, state: State) -> None:
        """Logic for updating Slack on Prefect flow cancellation"""
        await cls._send(flow, flow_run, state)
