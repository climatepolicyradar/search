"""OTel bootstrap for the vespa-feeder Prefect flow."""

import logging
import os
from pathlib import Path

from feeder_metrics import FeederMetrics
from observability.metrics import MetricsService
from observability.prefect_telemetry import PrefectTelemetry
from observability.service_manifest import ServiceManifest
from observability.telemetry_config import TelemetryConfig
from opentelemetry import trace

_MANIFEST_PATH = Path(__file__).parent / "service-manifest.json"
_logger = logging.getLogger(__name__)

# Short export interval for batch jobs — ensures metrics are exported before
# process exit even if force_flush() isn't called (mirrors data-in-pipeline).
os.environ.setdefault("METRICS_EXPORT_INTERVAL_MS", "5000")

_aws_env = os.getenv("AWS_ENV", "production")
_environment = "production" if "prod" in _aws_env else _aws_env

try:
    _config = TelemetryConfig.from_service_manifest(
        ServiceManifest.from_file(_MANIFEST_PATH),
        _environment,
        version="0.1.0",
    )
except Exception:
    _logger.exception("Failed to load service manifest, using defaults")
    _config = TelemetryConfig(
        service_name="search-vespa-feeder",
        namespace_name="data-ingestion",
        service_version="0.0.0",
        environment=_environment,
    )

_telemetry = PrefectTelemetry(config=_config)
_metrics_service = MetricsService(config=_config)
feeder_metrics = FeederMetrics(_metrics_service)
tracer = _telemetry.get_tracer() or trace.get_tracer("search-vespa-feeder")

_feed_stats: dict[str, int] = {}


def set_feed_stats(input_count: int, ok_count: int, total_errors: int) -> None:
    """Store feed stats so the Slack hook can include them in the notification."""
    global _feed_stats
    _feed_stats = {"input": input_count, "ok": ok_count, "errors": total_errors}


def get_feed_stats() -> dict[str, int]:
    return dict(_feed_stats)


def force_flush(timeout_millis: int = 10000) -> None:
    """Flush all pending metrics and logs. Call before the flow process exits."""
    ok = feeder_metrics.save_metrics(timeout_millis)
    if not ok:
        _logger.warning(
            "Metrics force_flush timed out or failed — some metrics may not have been exported"
        )
    else:
        _logger.info("Metrics force_flush succeeded")
    _telemetry.force_flush(timeout_millis)


def shutdown() -> None:
    """Flush and shut down all telemetry. Safe to call multiple times."""
    _metrics_service.shutdown()
    _telemetry.shutdown()
