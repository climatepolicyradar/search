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


API_TITLE = "Climate Policy Radar Search API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Full-text search across the world's climate laws, policies, litigation "
    "and finance documents — down to the exact passage, filterable by "
    "expert-curated concept."
)

logger.debug("🚀 Starting FastAPI application")
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
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


@app.exception_handler(VespaError)
async def handle_vespa_error(request: Request, exc: VespaError) -> JSONResponse:
    """
    Surface a failed Vespa request to the client.

    503: Vespa was unreachable, answered 5xx, or returned a body we could not parse.
    500: Vespa refused the query we built.
    429: Vespa throttled the query.
    404: This document is missing
    """
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    if exc.status_code is None:
        # retry: We don't know what the error was and will likely fix itself
        status_code = HTTPStatus.SERVICE_UNAVAILABLE
    elif (exc.status_code == HTTPStatus.TOO_MANY_REQUESTS):
        # retry: if you slow down, you can retry in a bit
        status_code = HTTPStatus.TOO_MANY_REQUESTS
    elif (exc.status_code == HTTPStatus.NOT_FOUND):
        # no-retry: this document is not there
        status_code = HTTPStatus.NOT_FOUND
    elif exc.status_code >= HTTPStatus.BAD_REQUEST and exc.status_code < HTTPStatus.INTERNAL_SERVER_ERROR:
        # no-retry: this is a search application error, and retrying will not fix it and potentially make it worse
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    elif exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        # retry: Vespa is having a bad day, and retrying later may work
        status_code = HTTPStatus.SERVICE_UNAVAILABLE
    
    logger.error(
        "Error: Vespa request failed while serving request method=%s path=%s "
        "(vespa_status=%s, returned_status=%s): %s",
        request.method,
        request.url.path,
        exc.status_code,
        status_code,
        exc,
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


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
async def root(request: Request):
    """
    Root endpoint: API information as schema.org JSON-LD.

    We use both routers to make sure we can have /search available publicly
    and / available to the ECS health check.
    """
    base = str(request.base_url).rstrip("/")
    return {
        "@context": "https://schema.org",
        "@type": "WebAPI",
        "name": API_TITLE,
        "version": API_VERSION,
        "description": API_DESCRIPTION,
        "url": f"{base}{router.prefix}",
        "documentation": [
            {
                "@type": "CreativeWork",
                "name": "llms.txt",
                "description": (
                    "How to query this API, written for LLMs and agents: the "
                    "data model, the filter grammar, sorting and freshness."
                ),
                "url": str(request.url_for("read_llms_txt")),
                "encodingFormat": "text/plain",
            },
            {
                "@type": "CreativeWork",
                "name": "OpenAPI schema",
                "description": (
                    "Machine-readable contract: response shapes, enum values "
                    "and parameter types."
                ),
                "url": f"{base}{app.openapi_url}",
                "encodingFormat": "application/json",
            },
        ],
        "provider": {
            "@type": "Organization",
            "name": "Climate Policy Radar CIC",
            "url": "https://climatepolicyradar.org",
        },
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{base}{router.prefix}/documents?query={{query}}",
                "contentType": "application/json",
            },
            "query-input": "required name=query",
        },
    }


app.include_router(router)


telemetry.instrument_fastapi(app)
telemetry.setup_exception_hook()
