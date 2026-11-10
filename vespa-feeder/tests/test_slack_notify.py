"""Unit tests for the Slack notification's feed-stats formatting."""

import asyncio
from types import SimpleNamespace

import pytest
import slack_notify
import telemetry
from prefect.runtime import deployment
from slack_notify import SlackNotify


@pytest.fixture(autouse=True)
def isolated_feed_stats(monkeypatch):
    """
    Give every test in this module its own empty `telemetry._feed_stats`.

    `_feed_stats` is module-level state that `set_feed_stats` mutates and never
    clears, so without this a test that sets it would leak into the next test
    here and into any later module that reads it. `monkeypatch.setattr` restores
    the original dict at teardown, which `set_feed_stats` rebinding the global
    does not undo on its own.

    This patches the real state rather than stubbing `slack_notify.get_feed_stats`
    deliberately: the bug under test (FUS-887) was that nothing ever called
    `set_feed_stats`, so the `set_feed_stats` -> `get_feed_stats` ->
    `_format_feed_stats` chain is exactly the seam worth exercising. Stubbing
    `get_feed_stats` would test the formatting against a fake the real code
    never uses.
    """
    monkeypatch.setattr(telemetry, "_feed_stats", {})


def test_format_feed_stats_renders_the_counts_that_were_set() -> None:
    """Once `set_feed_stats` has run, the real counts reach the Slack block."""
    telemetry.set_feed_stats(input_count=120, ok_count=118, total_errors=2)

    assert "in=120 ok=118 err=2" in SlackNotify._format_feed_stats()


def test_format_feed_stats_renders_zero_counts_rather_than_the_placeholder() -> None:
    """An all-zero feed is a real result, not a missing one, so it must not fall back to the em-dash."""
    telemetry.set_feed_stats(input_count=0, ok_count=0, total_errors=0)

    assert "in=0 ok=0 err=0" in SlackNotify._format_feed_stats()


def test_format_feed_stats_says_unknown_rather_than_the_placeholder_on_a_crash(
    monkeypatch,
) -> None:
    """
    A crash leaves no stats to read, and `—` reads as "zero records fed".

    The flow process dies before it sets them, and this hook runs in a
    different process which re-imports `telemetry` fresh - so the dict is
    empty whichever way round. The honest answer is that we do not know.
    """
    monkeypatch.setattr(deployment, "name", "search-vespa-feeder-passages")

    rendered = SlackNotify._format_feed_stats(crashed=True)

    assert "unknown" in rendered
    assert "`—`" not in rendered


def test_format_feed_stats_links_to_the_deployment_dashboard_on_a_crash(
    monkeypatch,
) -> None:
    """
    The counts survive the crash in Grafana, so the message points there.

    The run name is deliberately absent: `_build_blocks` already puts
    `{flow.name}/{deployment.name}/{flow_run.name}` in the header, so
    repeating it here is noise.
    """
    monkeypatch.setattr(deployment, "name", "search-vespa-feeder-passages")

    rendered = SlackNotify._format_feed_stats(crashed=True)

    assert "d/vespa-feeder-flows" in rendered
    assert "var-deployment_name=search-vespa-feeder-passages" in rendered


def test_format_feed_stats_prefers_real_counts_to_the_crash_wording() -> None:
    """
    A crash that somehow has stats reports them rather than claiming ignorance.

    `crashed=True` says the run crashed, not that the counts are unreadable;
    if they are there, they are better than a link.
    """
    telemetry.set_feed_stats(input_count=120, ok_count=118, total_errors=2)

    assert "in=120 ok=118 err=2" in SlackNotify._format_feed_stats(crashed=True)


def test_non_crash_paths_keep_the_placeholder() -> None:
    """
    Only the crash path changes. A cancel reaches the drain's `finally` and
    sets real stats, so its empty-dict case is a genuine anomaly worth
    showing as one rather than blaming on a crash.
    """
    assert SlackNotify._format_feed_stats() == "*Records fed*\n`—`"


def test_on_crashed_records_the_crash_and_flushes(monkeypatch) -> None:
    """
    The crash metric is emitted from the hook, and flushed before it returns.

    This is the only reporting channel a SIGKILL cannot take with it: every
    end-of-run signal in `vespa_feeder`'s `finally` runs inside the process
    that died. The hook's own process exits as soon as this returns, too
    soon for the ~5s periodic export, so the flush is what actually gets the
    counter out - without it the metric is recorded and then discarded.
    """
    monkeypatch.setattr(deployment, "name", "search-vespa-feeder-passages")
    recorded: list[dict] = []
    flushed: list[bool] = []
    monkeypatch.setattr(
        slack_notify.feeder_metrics,
        "record_run_crashed",
        lambda **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(slack_notify, "force_flush", lambda: flushed.append(True))
    # `_send` returns early outside prod, but assert the notification is still
    # reached rather than relying on that.
    sent: list[bool] = []

    async def _send(cls, flow, flow_run, state, crashed=False):  # noqa: ANN001, ARG001
        sent.append(crashed)

    monkeypatch.setattr(SlackNotify, "_send", classmethod(_send))

    asyncio.run(
        SlackNotify.on_crashed(
            flow=SimpleNamespace(name="search-vespa-feeder-passages"),
            flow_run=SimpleNamespace(name="ingenious-tarsier"),
            state=SimpleNamespace(name="Crashed"),
        )
    )

    assert recorded == [
        {
            "deployment_name": "search-vespa-feeder-passages",
            "run_name": "ingenious-tarsier",
        }
    ]
    assert flushed == [True]
    assert sent == [True]


def test_on_crashed_still_notifies_when_the_metric_fails(monkeypatch) -> None:
    """
    Telemetry failing must not also cost us the Slack alert.

    The hook runs in a short-lived process that may have no working exporter;
    a crash alert nobody sees is strictly worse than one without a metric.
    """
    monkeypatch.setattr(deployment, "name", "search-vespa-feeder-passages")

    def _boom(**kwargs) -> None:  # noqa: ANN003, ARG001
        raise RuntimeError("no exporter")

    monkeypatch.setattr(slack_notify.feeder_metrics, "record_run_crashed", _boom)
    sent: list[bool] = []

    async def _send(cls, flow, flow_run, state, crashed=False):  # noqa: ANN001, ARG001
        sent.append(crashed)

    monkeypatch.setattr(SlackNotify, "_send", classmethod(_send))

    asyncio.run(
        SlackNotify.on_crashed(
            flow=SimpleNamespace(name="search-vespa-feeder-passages"),
            flow_run=SimpleNamespace(name="ingenious-tarsier"),
            state=SimpleNamespace(name="Crashed"),
        )
    )

    assert sent == [True]
