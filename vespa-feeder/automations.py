"""
Prefect Automation guarding against wedged vespa-feeder runs.

Run with: uv run python vespa-feeder/automations.py

A `feed_batch` worker can wedge: the flow run sits in `Running` forever,
holding its ECS task, with no artifact and no Slack alert, until someone
notices and cancels it by hand. Heartbeats are the reliable signal here
(unlike logs, which can stall independently of the flow) - they fire every
~20-30s on a healthy run and stop dead the moment a run wedges. See
.claude/skills/prefect-vespa-feed-debug/SKILL.md for the full diagnosis
workflow this fits into.

This creates/updates a Proactive automation: if a matching flow run goes 15
minutes without a heartbeat, cancel it. Cancelling (rather than just
alerting) lets the ECS worker's own cancellation handling stop the
underlying Fargate task without a manual `aws ecs stop-task` - see
.claude/skills/prefect-vespa-feed-debug/SKILL.md for how to verify that by
hand if this automation doesn't catch something.

The `timeout_seconds` on each flow (passages_flow.py, documents_flow.py) is
the complementary guard: it bounds the worst case even if this automation is
ever disabled or mistuned, and - since it's a real TimedOut state rather
than a cancellation - it's what makes on_failure/on_crashed Slack hooks fire.
"""

import asyncio
from datetime import timedelta

from prefect.automations import Automation
from prefect.client.orchestration import get_client
from prefect.events.actions import CancelFlowRun
from prefect.events.schemas.automations import EventTrigger, Posture

_AUTOMATION_NAME = "vespa-feeder-stale-heartbeat-cancel"

# Must match the `name=` passed to @flow(...) in passages_flow.py / documents_flow.py.
_FEEDER_FLOW_NAMES = [
    "search-vespa-feeder-passages",
    "search-vespa-feeder-documents",
]

# Heartbeats fire roughly every 20-30s on a healthy run. 15 minutes of
# silence is ~30x that interval - comfortably past any transient blip, but
# still catches a wedge same-day instead of letting it run for days.
_STALE_AFTER = timedelta(minutes=15)


async def _flow_resource_ids(flow_names: list[str]) -> list[str]:
    async with get_client() as client:
        resource_ids = []
        for name in flow_names:
            flow = await client.read_flow_by_name(name)
            resource_ids.append(f"prefect.flow.{flow.id}")
        return resource_ids


async def main() -> None:
    flow_resource_ids = await _flow_resource_ids(_FEEDER_FLOW_NAMES)

    trigger = EventTrigger(
        match={"prefect.resource.id": "prefect.flow-run.*"},
        match_related={
            "prefect.resource.id": flow_resource_ids,
            "prefect.resource.role": "flow",
        },
        expect={"prefect.flow-run.heartbeat"},
        for_each={"prefect.resource.id"},
        posture=Posture.Proactive,
        within=_STALE_AFTER,
    )

    automation = Automation(
        name=_AUTOMATION_NAME,
        description=(
            "Cancels a vespa-feeder flow run after 15 minutes without a "
            "heartbeat - the signature of a wedged feed_batch worker."
            "@see: .claude/skills/prefect-vespa-feed-debug/SKILL.md."
        ),
        enabled=True,
        trigger=trigger,
        actions=[CancelFlowRun()],
    )

    try:
        existing = await Automation.aread(name=_AUTOMATION_NAME)
    except ValueError:
        existing = None

    if existing is None:
        await automation.acreate()
        print(f"Created automation {_AUTOMATION_NAME!r}")
    else:
        automation.id = existing.id
        await automation.aupdate()
        print(f"Updated automation {_AUTOMATION_NAME!r} ({existing.id})")


if __name__ == "__main__":
    asyncio.run(main())
