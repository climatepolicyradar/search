"""OTel bootstrap for the vespa-feeder Prefect flow."""

import atexit
import logging
import os
from pathlib import Path

from observability.base_telemetry import BaseTelemetry
from observability.service_manifest import ServiceManifest
from observability.telemetry_config import TelemetryConfig
from opentelemetry import trace
from opentelemetry.trace import Tracer

_MANIFEST_PATH = Path(__file__).parent / "service-manifest.json"

_telemetry: BaseTelemetry | None = None
_logger = logging.getLogger(__name__)


def setup_telemetry() -> Tracer:
    """Bootstrap OTel tracing and logging once per process. Returns the tracer."""
    global _telemetry
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
    atexit.register(_telemetry.shutdown)
    return _telemetry.get_tracer() or trace.get_tracer("search-vespa-feeder")
