import pytest
from vespa_feeder.stream.metrics import MetricsSink, RecordsLost
from vespa_feeder.stream.progress import VespaFeedStats
from vespa_feeder.stream.stream import Stream
from vespa_feeder.telemetry import get_feed_stats

from tests.stream.vespa_stats import vespa_stats


def snapshots(stats: list[VespaFeedStats]) -> Stream[VespaFeedStats]:
    yield from stats


def failing_after_three_of_five() -> Stream[VespaFeedStats]:
    yield vespa_stats(operations=5, ok=3)
    raise ValueError("feed broke")


def failing_after_one() -> Stream[VespaFeedStats]:
    yield vespa_stats(operations=1, ok=1)
    raise ValueError("feed broke")


def test_metrics_sink_completes_when_nothing_is_lost() -> None:
    sink = MetricsSink(deployment_name="deployment", run_name="run")
    stats = [vespa_stats(operations=1, ok=1), vespa_stats(operations=2, ok=2)]
    sink.drain(snapshots(stats))


def test_metrics_sink_ignores_records_not_yet_ok_mid_run() -> None:
    sink = MetricsSink(deployment_name="deployment", run_name="run")
    stats = [vespa_stats(operations=3, ok=1), vespa_stats(operations=3, ok=3)]
    sink.drain(snapshots(stats))


def test_metrics_sink_raises_when_the_final_stats_lost_records() -> None:
    sink = MetricsSink(deployment_name="deployment", run_name="run")
    stats = [vespa_stats(operations=1, ok=1), vespa_stats(operations=3, ok=1)]
    with pytest.raises(RecordsLost):
        sink.drain(snapshots(stats))


def test_metrics_sink_raises_when_the_stream_fails() -> None:
    sink = MetricsSink(deployment_name="deployment", run_name="run")
    with pytest.raises(ValueError):
        sink.drain(failing_after_one())


def test_metrics_sink_keeps_the_latest_counts_for_slack_when_the_stream_fails() -> None:
    sink = MetricsSink(deployment_name="deployment", run_name="run")
    with pytest.raises(ValueError):
        sink.drain(failing_after_three_of_five())
    assert get_feed_stats() == {"input": 5, "ok": 3, "errors": 2}
