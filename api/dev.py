import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.observability.src.api import (
    FastAPITelemetry,
    ServiceManifest,
    TelemetryConfig,
)
from api.routers import router
from search.log import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    yield
    # Shutdown: Cleanup (if needed)


# Configure Open Telemetry.
ENV = os.getenv("ENV", "staging")
os.environ["OTEL_PYTHON_LOG_CORRELATION"] = "True"
_api_dir = Path(__file__).parent
try:
    otel_config = TelemetryConfig.from_service_manifest(
        ServiceManifest.from_file(str(_api_dir / "service-manifest.json")),
        ENV,
        "0.1.0",
    )
except Exception as _:
    logger.exception("Failed to load service manifest, using defaults")
    otel_config = TelemetryConfig(
        service_name="search-api",
        namespace_name="data-querying",
        service_version="0.0.0",
        environment=ENV,
    )

telemetry = FastAPITelemetry(otel_config)
tracer = telemetry.get_tracer()


logger.debug("🚀 Starting FastAPI application")
app = FastAPI(
    title="Climate Policy Radar Search API",
    description="API for searching climate policy documents, passages, and labels",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/search/docs",
    redoc_url="/search/redoc",
    openapi_url="/search/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


telemetry.instrument_fastapi(app)
telemetry.setup_exception_hook()


# We use both routers to make sure we can have /search available publicly
# and / available to the AppRunner health check.
@app.get("/")
@router.get("")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Climate Policy Radar Search API",
        "version": "0.1.0",
    }
