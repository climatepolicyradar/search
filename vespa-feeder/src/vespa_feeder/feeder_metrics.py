"""
Feeder-specific metrics for the vespa-feeder service.

Defines FeederMetrics which uses MetricsService to create and manage
feed-specific metrics like record counts and durations.
"""

from typing import Optional

from opentelemetry.metrics import Counter, Histogram
from opentelemetry.metrics import _Gauge as Gauge

from vespa_feeder.observability.metrics import MetricsService


class FeederMetrics:
    """Vespa-feeder metrics using the MetricsService."""

    def __init__(self, metrics_service: MetricsService):
        self._metrics_service = metrics_service
        self._disabled = metrics_service._disabled

        self._records_fed: Optional[Counter] = None
        self._records_ok: Optional[Counter] = None
        self._records_error: Optional[Counter] = None
        self._records_skipped: Optional[Counter] = None
        self._run_duration: Optional[Histogram] = None
        self._last_run_duration: Optional[Gauge] = None
        self._runs_completed: Optional[Counter] = None
        self._runs_failed: Optional[Counter] = None
        self._runs_crashed: Optional[Counter] = None
        self._feeder_errors: Optional[Counter] = None
        self._throttled: Optional[Counter] = None
        self._other_http_errors: Optional[Counter] = None

        if not self._disabled:
            self._create_instruments()

    def _create_instruments(self) -> None:
        self._records_fed = self._metrics_service.create_counter(
            name="records.fed",
            description="Total records attempted to feed to Vespa",
            unit="1",
        )
        self._records_ok = self._metrics_service.create_counter(
            name="records.ok",
            description="Records successfully fed to Vespa",
            unit="1",
        )
        self._records_error = self._metrics_service.create_counter(
            name="records.error",
            description="Records that failed to feed to Vespa",
            unit="1",
        )
        self._records_skipped = self._metrics_service.create_counter(
            name="records.skipped",
            description="Records Vespa skipped because their content hash was unchanged",
            unit="1",
        )
        self._run_duration = self._metrics_service.create_histogram(
            name="run.duration",
            description="Total flow run duration in seconds",
            unit="s",
        )
        self._last_run_duration = self._metrics_service.create_gauge(
            name="last_run.duration",
            description="Duration of the most recently completed flow run in seconds",
            unit="s",
        )
        self._runs_completed = self._metrics_service.create_counter(
            name="runs.completed",
            description="Flow runs that completed successfully",
            unit="1",
        )
        self._runs_failed = self._metrics_service.create_counter(
            name="runs.failed",
            description="Flow runs that failed",
            unit="1",
        )
        self._runs_crashed = self._metrics_service.create_counter(
            name="runs.crashed",
            description="Flow runs that crashed (the process died, e.g. OOM/SIGKILL)",
            unit="1",
        )
        self._feeder_errors = self._metrics_service.create_counter(
            name="records.feeder_errors",
            description="Transport-layer failures with no HTTP response received",
            unit="1",
        )
        self._throttled = self._metrics_service.create_counter(
            name="records.throttled",
            description="Requests that got a 429 at some point (may have retried ok)",
            unit="1",
        )
        self._other_http_errors = self._metrics_service.create_counter(
            name="records.other_http_errors",
            description="Non-2xx responses other than 429, e.g. 5xx",
            unit="1",
        )

    def record_feed_stats(
        self,
        input_count: int,
        ok_count: int,
        skipped_count: int,
        total_errors: int,
        deployment_name: str,
        run_name: str = "",
    ) -> None:
        """Record fed, ok, skipped, and error record counts for a deployment run."""
        if self._disabled:
            return
        attrs = {"deployment_name": deployment_name, "run_name": run_name}
        if self._records_fed is not None:
            self._records_fed.add(input_count, attrs)
        if self._records_ok is not None:
            self._records_ok.add(ok_count, attrs)
        if self._records_skipped is not None:
            self._records_skipped.add(skipped_count, attrs)
        if self._records_error is not None:
            self._records_error.add(total_errors, attrs)

    def record_retry_stats(
        self,
        feeder_error_count: int,
        throttled_count: int,
        other_http_error_count: int,
        deployment_name: str,
        run_name: str = "",
    ) -> None:
        """
        Record a feed's retry attempts.

        Retries mostly self-heal and are not record loss - `records.error`
        is. Kept apart from `record_feed_stats` for that reason.
        """
        if self._disabled:
            return
        attrs = {"deployment_name": deployment_name, "run_name": run_name}
        if self._feeder_errors is not None:
            self._feeder_errors.add(feeder_error_count, attrs)
        if self._throttled is not None:
            self._throttled.add(throttled_count, attrs)
        if self._other_http_errors is not None:
            self._other_http_errors.add(other_http_error_count, attrs)

    def record_run_duration(
        self, duration_s: float, deployment_name: str, run_name: str = ""
    ) -> None:
        """Record the total duration of a flow run in seconds."""
        if self._disabled:
            return
        attrs = {"deployment_name": deployment_name, "run_name": run_name}
        if self._run_duration is not None:
            self._run_duration.record(duration_s, attrs)
        if self._last_run_duration is not None:
            self._last_run_duration.set(duration_s, attrs)

    def record_run_completed(self, deployment_name: str, run_name: str) -> None:
        """Increment the completed runs counter for a deployment run."""
        if self._disabled or self._runs_completed is None:
            return
        self._runs_completed.add(
            1, {"deployment_name": deployment_name, "run_name": run_name}
        )

    def record_run_failed(self, deployment_name: str, run_name: str) -> None:
        """Increment the failed runs counter for a deployment run."""
        if self._disabled or self._runs_failed is None:
            return
        self._runs_failed.add(
            1, {"deployment_name": deployment_name, "run_name": run_name}
        )

    def record_run_crashed(self, deployment_name: str, run_name: str) -> None:
        """
        Increment the crashed runs counter for a deployment run.

        Called from the `on_crashed` hook, not the flow - a crash kills the
        flow process before any of its own reporting runs.
        """
        if self._disabled or self._runs_crashed is None:
            return
        self._runs_crashed.add(
            1, {"deployment_name": deployment_name, "run_name": run_name}
        )

    def save_metrics(self, timeout_ms: int = 10000) -> bool:
        """Force flush all pending metrics. Call before process exit."""
        if self._disabled:
            return True
        return self._metrics_service.force_flush(timeout_ms)
