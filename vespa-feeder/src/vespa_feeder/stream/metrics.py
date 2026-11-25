from vespa_feeder.stream.progress import VespaFeedStats
from vespa_feeder.stream.stream import Stream
from vespa_feeder.telemetry import feeder_metrics, set_feed_stats


class RecordsLost(Exception):
    def __init__(self, stats: VespaFeedStats) -> None:
        super().__init__(f"{stats.lost} of {stats.operation_count} records lost")


class MetricsSink:
    def __init__(self, deployment_name: str, run_name: str) -> None:
        self._deployment_name = deployment_name
        self._run_name = run_name

    def drain(self, stats: Stream[VespaFeedStats]) -> None:
        """Record every stats snapshot, then the outcome of the run."""
        latest = VespaFeedStats.empty()
        try:
            for snapshot in stats:
                self._record(change=snapshot.since(latest), total=snapshot)
                latest = snapshot
        except BaseException:
            self._record_run_failed()
            raise

        feeder_metrics.record_run_duration(
            deployment_name=self._deployment_name,
            duration_s=latest.seconds,
            run_name=self._run_name,
        )

        if latest.lost > 0:
            self._record_run_failed()
            raise RecordsLost(latest)

        feeder_metrics.record_run_completed(
            deployment_name=self._deployment_name,
            run_name=self._run_name,
        )

    def _record(self, change: VespaFeedStats, total: VespaFeedStats) -> None:
        throttled = change.response_code_counts.get(429, 0)

        feeder_metrics.record_feed_stats(
            total_errors=change.lost,
            deployment_name=self._deployment_name,
            input_count=change.operation_count,
            ok_count=change.ok_count,
            run_name=self._run_name,
        )

        feeder_metrics.record_retry_stats(
            other_http_error_count=change.response_error_count - throttled,
            feeder_error_count=change.error_count,
            deployment_name=self._deployment_name,
            throttled_count=throttled,
            run_name=self._run_name,
            file_count=0,
        )

        set_feed_stats(
            total_errors=total.lost,
            input_count=total.operation_count,
            ok_count=total.ok_count,
        )

    def _record_run_failed(self) -> None:
        feeder_metrics.record_run_failed(
            deployment_name=self._deployment_name,
            run_name=self._run_name,
        )
