"""
Feeder-specific metrics for the vespa-feeder service.

Defines FeederMetrics which uses MetricsService to create and manage
feed-specific metrics like record counts and durations.
"""

from typing import Optional

from observability.metrics import MetricsService
from opentelemetry.metrics import Counter, Histogram


class FeederMetrics:
    """Vespa-feeder metrics using the MetricsService."""

    def __init__(self, metrics_service: MetricsService):
        self._metrics_service = metrics_service
        self._disabled = metrics_service._disabled

        self._records_fed: Optional[Counter] = None
        self._records_ok: Optional[Counter] = None
        self._records_error: Optional[Counter] = None
        self._run_duration: Optional[Histogram] = None
        self._task_duration: Optional[Histogram] = None
        self._runs_completed: Optional[Counter] = None
        self._runs_failed: Optional[Counter] = None

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
        self._run_duration = self._metrics_service.create_histogram(
            name="run.duration",
            description="Total flow run duration in seconds",
            unit="s",
        )
        self._task_duration = self._metrics_service.create_histogram(
            name="task.duration",
            description="Task duration in seconds",
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

    def record_feed_stats(
        self,
        input_count: int,
        ok_count: int,
        total_errors: int,
        deployment_name: str,
        run_name: str = "",
    ) -> None:
        """Record fed, ok, and error record counts for a deployment run."""
        if self._disabled:
            return
        attrs = {"deployment_name": deployment_name, "run_name": run_name}
        if self._records_fed is not None:
            self._records_fed.add(input_count, attrs)
        if self._records_ok is not None:
            self._records_ok.add(ok_count, attrs)
        if self._records_error is not None:
            self._records_error.add(total_errors, attrs)

    def record_run_duration(self, duration_s: float, deployment_name: str) -> None:
        """Record the total duration of a flow run in seconds."""
        if self._disabled or self._run_duration is None:
            return
        self._run_duration.record(duration_s, {"deployment_name": deployment_name})

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

    def record_task_duration(
        self, task_name: str, duration_s: float, deployment_name: str
    ) -> None:
        """Record the duration of an individual task in seconds."""
        if self._disabled or self._task_duration is None:
            return
        self._task_duration.record(
            duration_s, {"deployment_name": deployment_name, "task_name": task_name}
        )

    def save_metrics(self, timeout_ms: int = 10000) -> bool:
        """Force flush all pending metrics. Call before process exit."""
        if self._disabled:
            return True
        return self._metrics_service.force_flush(timeout_ms)
