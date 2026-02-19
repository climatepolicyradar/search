from contextlib import asynccontextmanager
from typing import Annotated, TypeVar

from fastapi import APIRouter, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel

from search.data_in_models import Document, Label
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
)
from search.log import get_logger

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


class SearchResponse[T](BaseModel):
    """Response model for search results"""

    total_results: int | None = None
    page: int
    page_size: int
    total_pages: int | None
    next_page: AnyHttpUrl | None = None
    previous_page: AnyHttpUrl | None = None
    results: list[T]


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
    # we used `alias` here as so that the query param follows the JSON path of the response model
    # and we cannot use `.` in python value names.
    labels_id_and: list[str] | None = Query(None, alias="labels.label.id"),
    labels_id_or: list[str] | None = Query(None, alias="or:labels.label.id"),
    labels_id_not: list[str] | None = Query(None, alias="not:labels.label.id"),
    filters_json_string: str | None = Query(None, alias="filters"),
    limit: int = 10,
    offset: int = 0,
):

    results = DevVespaDocumentSearchEngine().search(
        query=query,
        labels_id_and=labels_id_and,
        labels_id_or=labels_id_or,
        labels_id_not=labels_id_not,
        filters_json_string=filters_json_string,
        limit=limit,
        offset=offset,
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
    )


@router.get("/labels", response_model=SearchResponse[Label])
def read_labels(
    query: Annotated[
        str, Query(..., description="What are you looking for?", min_length=1)
    ],
):
    results = DevVespaLabelSearchEngine().search(query=query)
    # TODO: pagination
    return SearchResponse[Label](
        total_results=len(results),
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results,
    )


# endregion

app.include_router(router)
