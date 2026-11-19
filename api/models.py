from typing import TypeVar

from pydantic import AnyHttpUrl, BaseModel

from search.log import get_logger

logger = get_logger(__name__)


T = TypeVar("T", bound=BaseModel)


class ItemResponse[T](BaseModel):
    data: T


class SearchResponse[T](BaseModel):
    """Response model for search results."""

    took_ms: int | None = None
    total_size: int | None = None
    page: int
    page_size: int
    total_pages: int | None
    next_page: AnyHttpUrl | None = None
    previous_page: AnyHttpUrl | None = None
    results: list[T]
    debug_info: list[dict] | None = None
