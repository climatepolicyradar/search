"""
Feeder-specific metrics for the vespa-feeder service.

Defines FeederMetrics which uses MetricsService to create and manage
feed-specific metrics like record counts and durations.
"""

from typing import Optional

from observability.metrics import MetricsService
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.metrics import _Gauge as Gauge


class FeederMetrics:
    """Vespa-feeder metrics using the MetricsService."""

    def __init__(self, metrics_service: MetricsService):
        self._metrics_service = metrics_service
        self._disabled = metrics_service._disabled

        self._records_fed: Optional[Counter] = None
        self._records_ok: Optional[Counter] = None
        self._records_error: Optional[Counter] = None
        self._run_duration: Optional[Histogram] = None
        self._last_run_duration: Optional[Gauge] = None
        self._task_duration: Optional[Histogram] = None
        self._runs_completed: Optional[Counter] = None
        self._runs_failed: Optional[Counter] = None
        self._runs_crashed: Optional[Counter] = None
        self._batches_expected: Optional[Gauge] = None
        self._batches_completed: Optional[Counter] = None
        self._feeder_errors: Optional[Counter] = None
        self._throttled: Optional[Counter] = None
        self._other_http_errors: Optional[Counter] = None
        self._files_fed: Optional[Counter] = None

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
        self._last_run_duration = self._metrics_service.create_gauge(
            name="last_run.duration",
            description="Duration of the most recently completed flow run in seconds",
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
        self._runs_crashed = self._metrics_service.create_counter(
            name="runs.crashed",
            description="Flow runs that crashed (the process died, e.g. OOM/SIGKILL)",
            unit="1",
        )
        self._batches_expected = self._metrics_service.create_gauge(
            name="run.batches_expected",
            description="Batches queued for this run, emitted before any feeding starts",
            unit="1",
        )
        self._batches_completed = self._metrics_service.create_counter(
            name="run.batches_completed",
            description="Batches that finished feeding in this run",
            unit="1",
        )
        # The three retry signals below are transport/HTTP attempts that mostly
        # self-heal. They are not record loss - `records.error` is - and are
        # recorded for diagnostic context only.
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
        self._files_fed = self._metrics_service.create_counter(
            name="run.files_fed",
            description="Files fed to Vespa in this run",
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

    def record_retry_stats(
        self,
        feeder_error_count: int,
        throttled_count: int,
        other_http_error_count: int,
        file_count: int,
        deployment_name: str,
        run_name: str = "",
    ) -> None:
        """
        Record a batch's retry attempts and the files it fed.

        Kept apart from `record_feed_stats` because these are a different
        kind of fact: transport and HTTP retries that mostly self-heal, not
        the outcome of the feed. Summed per run they are what the dashboard's
        Runs table reports as "Retry Attempts", for diagnostic context beside
        the records actually lost.
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
        if self._files_fed is not None:
            self._files_fed.add(file_count, attrs)

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

        Called from the `on_crashed` hook rather than the flow, because a
        crash is the process dying: nothing in the flow gets to run. The
        hook's process is the only one still alive to report it.
        """
        if self._disabled or self._runs_crashed is None:
            return
        self._runs_crashed.add(
            1, {"deployment_name": deployment_name, "run_name": run_name}
        )

    def record_batches_expected(
        self, batch_count: int, deployment_name: str, run_name: str
    ) -> None:
        """
        Record how many batches this run queued.

        The denominator for `run.batches_completed`. Set once, before any
        feeding, so a run that dies early still reports what it set out to do.
        """
        if self._disabled or self._batches_expected is None:
            return
        self._batches_expected.set(
            batch_count, {"deployment_name": deployment_name, "run_name": run_name}
        )

    def record_batch_completed(self, deployment_name: str, run_name: str) -> None:
        """Increment the completed batches counter for a deployment run."""
        if self._disabled or self._batches_completed is None:
            return
        self._batches_completed.add(
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
