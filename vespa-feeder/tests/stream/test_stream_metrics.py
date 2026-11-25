import pytest
from vespa_feeder.stream.metrics import MetricsSink, RecordsLost
from vespa_feeder.stream.progress import VespaFeedStats
from vespa_feeder.stream.stream import Stream

from tests.stream.vespa_stats import vespa_stats


def snapshots(stats: list[VespaFeedStats]) -> Stream[VespaFeedStats]:
    yield from stats


def failing_after_one() -> Stream[VespaFeedStats]:
    yield vespa_stats(operations=1, ok=1)
    raise ValueError("feed broke")


def test_metrics_sink_completes_when_nothing_is_lost() -> None:
    stats = [vespa_stats(operations=1, ok=1), vespa_stats(operations=2, ok=2)]
    MetricsSink(deployment_name="deployment", run_name="run").drain(snapshots(stats))


def test_metrics_sink_raises_when_the_last_snapshot_lost_records() -> None:
    stats = [vespa_stats(operations=1, ok=1), vespa_stats(operations=3, ok=1)]
    with pytest.raises(RecordsLost):
        MetricsSink(deployment_name="deployment", run_name="run").drain(
            snapshots(stats)
        )


def test_metrics_sink_raises_when_the_stream_fails() -> None:
    with pytest.raises(ValueError):
        MetricsSink(deployment_name="deployment", run_name="run").drain(
            failing_after_one()
        )
