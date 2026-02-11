from contextlib import asynccontextmanager
from typing import Annotated, TypeVar

from fastapi import APIRouter, FastAPI, Query
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
    query: Annotated[
        str, Query(..., description="What are you looking for?", min_length=1)
    ],
    limit: int = 10,
    offset: int = 0,
):
    results = DevVespaDocumentSearchEngine().search(
        query=query, limit=limit, offset=offset
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


app.include_router(router)
