"""OTel bootstrap for the vespa-feeder Prefect flow."""

import atexit
import logging
import os
from pathlib import Path

from observability.base_telemetry import BaseTelemetry
from observability.metrics import MetricsService
from observability.service_manifest import ServiceManifest
from observability.telemetry_config import TelemetryConfig
from opentelemetry import trace
from opentelemetry.trace import Tracer

_MANIFEST_PATH = Path(__file__).parent / "service-manifest.json"

_telemetry: BaseTelemetry | None = None
_metrics: MetricsService | None = None
_logger = logging.getLogger(__name__)

_feed_stats: dict[str, int] = {}


def set_feed_stats(input_count: int, ok_count: int, total_errors: int) -> None:
    """Store feed stats so the Slack hook can include them in the notification."""
    global _feed_stats
    _feed_stats = {"input": input_count, "ok": ok_count, "errors": total_errors}


def get_feed_stats() -> dict[str, int]:
    return dict(_feed_stats)


def setup_telemetry() -> Tracer:
    """Bootstrap OTel tracing, logging, and metrics once per process. Returns the tracer."""
    global _telemetry, _metrics
    if _telemetry is not None:
        return _telemetry.get_tracer() or trace.get_tracer("search-vespa-feeder")

    environment = os.getenv("AWS_ENV", "sandbox")

    try:
        config = TelemetryConfig.from_service_manifest(
            ServiceManifest.from_file(_MANIFEST_PATH),
            environment,
            version="0.1.0",
        )
    except Exception:
        _logger.exception("Failed to load service manifest, using defaults")
        config = TelemetryConfig(
            service_name="search-vespa-feeder",
            namespace_name="data-ingestion",
            service_version="0.0.0",
            environment=environment,
        )

    _telemetry = BaseTelemetry(config)
    _metrics = MetricsService(config)
    atexit.register(_shutdown)
    return _telemetry.get_tracer() or trace.get_tracer("search-vespa-feeder")


def record_feed_stats(ok_count: int, total_errors: int, deployment_name: str) -> None:
    """Record Vespa feed record counts as RED Rate/Error metrics."""
    if _metrics is None:
        return
    counter = _metrics.create_counter(
        "records.fed", unit="records", description="Records submitted to Vespa"
    )
    if counter is None:
        return
    counter.add(ok_count, {"deployment_name": deployment_name, "status": "ok"})
    if total_errors:
        counter.add(
            total_errors, {"deployment_name": deployment_name, "status": "error"}
        )


def record_run_duration(duration_s: float, deployment_name: str) -> None:
    """Record total flow run duration."""
    if _metrics is None:
        return
    histogram = _metrics.create_histogram(
        "run.duration", unit="s", description="Total flow run duration in seconds"
    )
    if histogram is None:
        return
    histogram.record(duration_s, {"deployment_name": deployment_name})


def record_task_duration(
    task_name: str, duration_s: float, deployment_name: str
) -> None:
    """Record per-task duration, allowing step-level breakdown."""
    if _metrics is None:
        return
    histogram = _metrics.create_histogram(
        "task.duration", unit="s", description="Task duration in seconds"
    )
    if histogram is None:
        return
    histogram.record(
        duration_s, {"deployment_name": deployment_name, "task_name": task_name}
    )


def force_flush(timeout_millis: int = 10000) -> None:
    """Flush all pending metrics and logs. Call before the flow process exits."""
    if _metrics is not None:
        _metrics.force_flush(timeout_millis)
    if _telemetry is not None:
        _telemetry.force_flush(timeout_millis)


def _shutdown() -> None:
    if _metrics is not None:
        _metrics.shutdown()
    if _telemetry is not None:
        _telemetry.shutdown()
