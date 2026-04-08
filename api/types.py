from typing import TypeVar

from pydantic import AnyHttpUrl, BaseModel

from search.engines.dev_vespa import (
    CountAggregation,
)
from search.label import Label
from search.log import get_logger

logger = get_logger(__name__)


T = TypeVar("T", bound=BaseModel)


class Aggregations(BaseModel):
    labels: list[CountAggregation[Label]]


class SearchResponse[T](BaseModel):
    """Response model for search results."""

    total_size: int | None = None
    page: int
    page_size: int
    total_pages: int | None
    next_page: AnyHttpUrl | None = None
    previous_page: AnyHttpUrl | None = None
    results: list[T]
    aggregations: Aggregations | None = None
    debug_info: list[dict] | None = None
