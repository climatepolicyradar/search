from typing import TypeVar

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from search.engines.dev_vespa import (
    CountAggregation,
)
from search.label import Label
from search.log import get_logger

logger = get_logger(__name__)


T = TypeVar("T", bound=BaseModel)


class Aggregations(BaseModel):
    labels: list[CountAggregation[Label]]


class Facets(BaseModel):
    # This allows pydantic to populate via the alias names or pythonic snake_case names.
    # e.g. both labels.value.type & labels_value_type
    model_config = ConfigDict(populate_by_name=True)

    labels_value_type: dict[str, list[CountAggregation[Label]]] | None = Field(
        None, alias="labels.value.type"
    )
    labels_type: dict[str, list[CountAggregation[Label]]] | None = Field(
        None, alias="labels.type"
    )


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
    aggregations: Aggregations | None = None
    facets: Facets | None = None
    debug_info: list[dict] | None = None
