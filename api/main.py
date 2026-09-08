import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.observability.src.api import (
    FastAPITelemetry,
    MetricsService,
    ServiceManifest,
    TelemetryConfig,
)
from api.routers import router
from api.search_metrics import SearchMetrics
from search.engines import VespaError
from search.log import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    yield
    # Shutdown: Cleanup (if needed)


# Configure Open Telemetry.
ENV = os.getenv("ENV", "development")
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
metrics_service = MetricsService(otel_config)
search_metrics = SearchMetrics(metrics_service)


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


VESPA_UNAVAILABLE_DETAIL = "Search service unavailable"


@app.exception_handler(VespaError)
async def handle_vespa_error(request: Request, exc: VespaError) -> JSONResponse:
    """
    Surface a failed Vespa request to the client as HTTP 503.

    Registered once, application-wide, so that every route - including ones
    added later - reports backend failure rather than an empty result set. The
    exception detail is logged but not returned: it can contain the Vespa
    response body.
    """
    logger.error(
        "Error: Vespa unavailable while serving request method=%s path=%s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        content={"detail": VESPA_UNAVAILABLE_DETAIL},
    )


@app.middleware("http")
async def log_request_lifecycle(request: Request, call_next):
    """Log incoming API requests with outcome and latency."""
    start_time = perf_counter()
    route_path = getattr(request.scope.get("route"), "path", request.url.path)
    logger.debug(
        "Incoming request: method=%s path=%s query=%s",
        request.method,
        route_path,
        request.url.query,
    )
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = search_metrics.elapsed_ms(start_time)
        search_metrics.record_error(
            method=request.method,
            path=route_path,
            duration_ms=duration_ms,
        )
        logger.exception(
            "Error: Unhandled exception while serving request method=%s path=%s "
            "duration_ms=%s",
            request.method,
            route_path,
            duration_ms,
        )
        raise

    duration_ms = search_metrics.elapsed_ms(start_time)
    search_metrics.record_success(
        method=request.method,
        path=route_path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    # An error response logged at INFO as "Success" is invisible to log grepping
    # and error alerting. A 4xx is us correctly refusing a bad request, so it is
    # not our failure - but it is not a success either, and a burst of them is
    # usually a caller bug worth seeing, so it warns rather than sinking into
    # the INFO stream.
    status_log = "%s: Request completed method=%s path=%s status_code=%s duration_ms=%s"
    status_log_args = (request.method, route_path, response.status_code, duration_ms)
    if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error(status_log, "Error", *status_log_args)
    elif response.status_code >= HTTPStatus.BAD_REQUEST:
        logger.warning(status_log, "Rejected", *status_log_args)
    else:
        logger.info(status_log, "Success", *status_log_args)
    return response


@app.get("/")
@router.get("")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Climate Policy Radar Search API",
        "version": "0.1.0",
    }


app.include_router(router)


telemetry.instrument_fastapi(app)
telemetry.setup_exception_hook()


# We use both routers to make sure we can have /search available publicly
# and / available to the AppRunner health check.
