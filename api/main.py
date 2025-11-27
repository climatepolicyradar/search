from pathlib import Path
from typing import Annotated, Callable, Generic, TypeVar

from fastapi import Depends, FastAPI, Query, Request
from pydantic import AnyHttpUrl, BaseModel

from search.document import Document
from search.engines import SearchEngine
from search.engines.json import (
    JSONDocumentSearchEngine,
    JSONLabelSearchEngine,
    JSONPassageSearchEngine,
)
from search.label import Label
from search.passage import Passage

app = FastAPI(
    title="Climate Policy Radar Search API",
    description="API for searching climate policy documents, passages, and labels",
    version="0.1.0",
)

T = TypeVar("T", bound=BaseModel)


class SearchResponse(BaseModel, Generic[T]):
    """Response model for search results"""

    total_results: int
    page: int
    page_size: int
    total_pages: int
    next_page: AnyHttpUrl | None = None
    previous_page: AnyHttpUrl | None = None
    results: list[T]


def get_label_search_engine() -> SearchEngine:
    """Get the label search engine instance."""
    return JSONLabelSearchEngine(str(Path("data/labels.jsonl")))


def get_passage_search_engine() -> SearchEngine:
    """Get the passage search engine instance."""
    return JSONPassageSearchEngine(str(Path("data/passages.jsonl")))


def get_document_search_engine() -> SearchEngine:
    """Get the document search engine instance."""
    return JSONDocumentSearchEngine(str(Path("data/documents.jsonl")))


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
        page: Annotated[int, Query(description="Page number", ge=1)] = 1,
        page_size: Annotated[int, Query(description="Page size", ge=1, le=100)] = 10,
        engine: SearchEngine = Depends(engine_dependency),
    ) -> SearchResponse[T]:
        """Search endpoint for the specified resource."""
        results = engine.search(search_terms)
        total_results = len(results)
        total_pages = (
            (total_results + page_size - 1) // page_size if total_results > 0 else 0
        )
        start_idx = page_size * (page - 1)
        end_idx = start_idx + page_size
        paginated_results = results[start_idx:end_idx]

        # Build pagination URLs
        next_page = None
        if page < total_pages:
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
        "endpoints": {
            "documents": "/documents",
            "passages": "/passages",
            "labels": "/labels",
        },
    }


app.get("/documents", response_model=SearchResponse[Document])(
    create_search_endpoint(Document, get_document_search_engine)
)

app.get("/passages", response_model=SearchResponse[Passage])(
    create_search_endpoint(Passage, get_passage_search_engine)
)

app.get("/labels", response_model=SearchResponse[Label])(
    create_search_endpoint(Label, get_label_search_engine)
)
