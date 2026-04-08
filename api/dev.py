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


@router.get("/documents", response_model=SearchResponse[Document])
def read_documents(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(None, alias="filters"),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(order_by),
    debug: bool = False,
    bolding: bool = False,
    principal_label_boost_factor: float | None = None,
):
    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=bolding
    )
    results = engine.search(
        query=query,
        pagination=pagination,
        order_by=order_by,
        filters_json_string=filters_json_string,
        principal_label_boost_factor=principal_label_boost_factor,
    )

    # TODO: pagination
    return SearchResponse[Document](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        debug_info=engine.last_debug_info if debug else None,
        aggregations=Aggregations(
            labels=engine.aggregations(
                query=query,
                filters_json_string=filters_json_string,
            )
        ),
    )


@router.get("/labels", response_model=SearchResponse[Label])
def read_labels(
    query: str | None = Query(None, description="What are you looking for?"),
    type: str | None = None,
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(order_by),
):
    engine = DevVespaLabelSearchEngine(settings=settings)
    results = engine.search(
        query=query, pagination=pagination, order_by=order_by, label_type=type
    )
    engine.all_label_types()

    return SearchResponse[Label](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        aggregations=None,
    )


@router.get("/passages", response_model=SearchResponse[Passage])
def read_passages(
    query: str | None = Query(None, description="What are you looking for?"),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(order_by),
):
    engine = DevVespaPassageSearchEngine(settings=settings)
    results = engine.search(
        query=query,
        pagination=pagination,
        order_by=order_by,
    )

    return SearchResponse[Passage](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        aggregations=None,
    )


# endregion

app.include_router(router)
