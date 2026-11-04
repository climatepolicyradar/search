"""Unit tests for the Slack notification's feed-stats formatting."""

import pytest
import telemetry
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


def test_format_feed_stats_without_stats_renders_the_placeholder() -> None:
    """With no stats recorded, Slack shows the em-dash - the visible symptom of FUS-887."""
    assert SlackNotify._format_feed_stats() == "*Records fed*\n`—`"


def test_format_feed_stats_renders_the_counts_that_were_set() -> None:
    """Once `set_feed_stats` has run, the real counts reach the Slack block."""
    telemetry.set_feed_stats(input_count=120, ok_count=118, total_errors=2)

    assert SlackNotify._format_feed_stats() == "*Records fed*\n`in=120 ok=118 err=2`"


def test_format_feed_stats_renders_zero_counts_rather_than_the_placeholder() -> None:
    """An all-zero feed is a real result, not a missing one, so it must not fall back to the em-dash."""
    telemetry.set_feed_stats(input_count=0, ok_count=0, total_errors=0)

    assert SlackNotify._format_feed_stats() == "*Records fed*\n`in=0 ok=0 err=0`"
