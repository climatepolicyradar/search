from vespa_feeder.stream.progress import VespaFeedStats
from vespa_feeder.stream.stream import Stream
from vespa_feeder.telemetry import feeder_metrics, set_feed_stats


class RecordsLost(Exception):
    def __init__(self, lost: int, operations: int) -> None:
        super().__init__(f"{lost} of {operations} records lost")


def _lost(stats: VespaFeedStats) -> int:
    unchanged = stats.response_codes.get(412, 0)
    return stats.operation_count - stats.ok_count - unchanged


class MetricsSink:
    def __init__(self, deployment_name: str, run_name: str) -> None:
        self._deployment_name = deployment_name
        self._run_name = run_name

    def drain(self, stats: Stream[VespaFeedStats]) -> None:
        """Record every stats snapshot, then the outcome of the run."""
        final = VespaFeedStats.empty()
        try:
            for snapshot in stats:
                self._record_progress(change=snapshot.since(final), latest=snapshot)
                final = snapshot
        except Exception:
            self._record_final(final=final)
            self._record_run_failed()
            raise

        self._record_final(final=final)
        lost = _lost(final)

        if lost > 0:
            self._record_run_failed()
            raise RecordsLost(lost=lost, operations=final.operation_count)

        feeder_metrics.record_run_completed(
            deployment_name=self._deployment_name,
            run_name=self._run_name,
        )

    def _record_progress(self, change: VespaFeedStats, latest: VespaFeedStats) -> None:
        throttled = change.response_codes.get(429, 0)

        feeder_metrics.record_feed_stats(
            deployment_name=self._deployment_name,
            input_count=change.operation_count,
            ok_count=change.ok_count,
            run_name=self._run_name,
            total_errors=0,
        )

        feeder_metrics.record_retry_stats(
            other_http_error_count=change.response_error_count - throttled,
            feeder_error_count=change.error_count,
            deployment_name=self._deployment_name,
            throttled_count=throttled,
            run_name=self._run_name,
        )

        set_feed_stats(
            total_errors=_lost(latest),
            input_count=latest.operation_count,
            ok_count=latest.ok_count,
        )

    def _record_final(self, final: VespaFeedStats) -> None:
        feeder_metrics.record_feed_stats(
            total_errors=_lost(final),
            deployment_name=self._deployment_name,
            run_name=self._run_name,
            input_count=0,
            ok_count=0,
        )

        feeder_metrics.record_run_duration(
            deployment_name=self._deployment_name,
            duration_s=final.seconds,
            run_name=self._run_name,
        )

    def _record_run_failed(self) -> None:
        feeder_metrics.record_run_failed(
            deployment_name=self._deployment_name,
            run_name=self._run_name,
        )
