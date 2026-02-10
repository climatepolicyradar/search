import time
from contextlib import asynccontextmanager
from typing import Annotated, Callable, Generic, TypeVar

from fastapi import Depends, FastAPI, Query, Request
from pydantic import AnyHttpUrl, BaseModel

from search.engines import SearchEngine
from search.engines.dev_vespa import DevVespaDocumentSearchEngine
from search.log import get_logger
from search.models import Document

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    yield
    # Shutdown: Cleanup (if needed)


app = FastAPI(
    title="Climate Policy Radar Search API",
    description="API for searching climate policy documents, passages, and labels",
    version="0.1.0",
    lifespan=lifespan,
)

T = TypeVar("T", bound=BaseModel)


class SearchResponse(BaseModel, Generic[T]):
    """Response model for search results"""

    total_results: int | None = None
    page: int
    page_size: int
    total_pages: int | None
    next_page: AnyHttpUrl | None = None
    previous_page: AnyHttpUrl | None = None
    results: list[T]


def build_pagination_url(
    request: Request,
    search_terms: str,
    page: int,
    page_size: int,
) -> str:
    """Build a pagination URL with the given parameters."""
    url = request.url.replace_query_params(
        search_terms=search_terms,
        page=page,
        page_size=page_size,
    )
    return str(url)


def create_search_endpoint(
    resource_class: type[T], engine_dependency: Callable[[], SearchEngine]
):
    """
    Factory function to create a search endpoint.

    :param resource_class: The resource class (e.g., Document, Passage, Label)
    :param engine_dependency: Dependency function that returns a search engine
    :return: Async endpoint function
    """

    async def search_endpoint(
        request: Request,
        search_terms: Annotated[
            str, Query(..., description="What are you looking for?", min_length=1)
        ],
        page: Annotated[int, Query(description="Page number (1 indexed)", ge=1)] = 1,
        page_size: Annotated[int, Query(description="Page size", ge=1, le=100)] = 10,
        count: Annotated[
            bool,
            Query(
                description="Whether to return result count and number of pages. Recommended to set to False for datasets in the size of millions.",
                alias="count",
            ),
        ] = False,
        engine: SearchEngine = Depends(engine_dependency),
    ) -> SearchResponse[T]:
        """Search endpoint for the specified resource."""

        if count:
            logger.info("Counting total results...")
            start = time.time()
            total_results = engine.count(search_terms)
            elapsed = time.time() - start
            logger.info(f"{total_results} results found in {elapsed:.1f} seconds")

            total_pages = (
                (total_results + page_size - 1) // page_size if total_results > 0 else 0
            )
        else:
            total_results = None
            total_pages = None

        offset = page_size * (page - 1)

        logger.info(
            f"Running search for {search_terms} with limit {page_size} and offset {offset}..."
        )
        start = time.time()
        paginated_results = engine.search(search_terms, limit=page_size, offset=offset)
        elapsed = time.time() - start
        logger.info(f"Search complete in {elapsed:.1f} seconds")

        # Build pagination URLs
        next_page_likely_exists = len(paginated_results) == page_size

        next_page = None
        if next_page_likely_exists:
            next_page = AnyHttpUrl(
                build_pagination_url(request, search_terms, page + 1, page_size)
            )

        previous_page = None
        if page > 1:
            previous_page = AnyHttpUrl(
                build_pagination_url(request, search_terms, page - 1, page_size)
            )

        return SearchResponse[T](
            total_results=total_results,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            next_page=next_page,
            previous_page=previous_page,
            results=paginated_results,
        )

    # Set endpoint docstring using the class name
    search_endpoint.__doc__ = (
        f"Search for {resource_class.__name__.lower()}s matching the query terms."
    )
    return search_endpoint


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Climate Policy Radar Search API",
        "version": "0.1.0",
    }


app.get("/documents", response_model=SearchResponse[Document])(
    create_search_endpoint(Document, DevVespaDocumentSearchEngine)
)
