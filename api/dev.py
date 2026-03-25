from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import APIRouter, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel

from search.data_in_models import Document
from search.engines.dev_vespa import (
    CountAggregation,
    DevVespaDocumentSearchEngine,
    DevVespaLabelTypeaheadSearchEngine,
    DevVespaPassageSearchEngine,
)
from search.label import Label
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    yield
    # Shutdown: Cleanup (if needed)


router = APIRouter(
    prefix="/search",
)
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

T = TypeVar("T", bound=BaseModel)


class Aggregations(BaseModel):
    labels: list[CountAggregation[Label]]


class SearchResponse[T](BaseModel):
    """Response model for search results."""

    total_results: int | None = None
    page: int
    page_size: int
    total_pages: int | None
    next_page: AnyHttpUrl | None = None
    previous_page: AnyHttpUrl | None = None
    results: list[T]
    aggregations: Aggregations | None = None
    debug_info: list[dict] | None = None


# region routes
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
    page_token: int = 1,
    page_size: int = 10,
    debug: bool = False,
):
    engine = DevVespaDocumentSearchEngine(debug=debug)
    results = engine.search(
        query=query,
        filters_json_string=filters_json_string,
        page_token=page_token,
        page_size=page_size,
    )

    # TODO: pagination
    return SearchResponse[Document](
        total_results=len(results),
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results,
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
):
    engine = DevVespaLabelTypeaheadSearchEngine()
    results = engine.search(query=query, label_type=type)
    engine.all_label_types()

    return SearchResponse[Label](
        total_results=len(results),
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results,
        aggregations=None,
    )


@router.get("/passages", response_model=SearchResponse[Passage])
def read_passages(
    query: str | None = Query(None, description="What are you looking for?"),
    page_token: int = 1,
    page_size: int = 10,
):
    engine = DevVespaPassageSearchEngine()
    results = engine.search(
        query=query,
        page_token=page_token,
        page_size=page_size,
    )

    return SearchResponse[Passage](
        total_results=len(results),
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results,
        aggregations=[],
    )


# endregion

app.include_router(router)
