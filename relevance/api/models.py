from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from api.utils import RankProfile


class FieldFilter(BaseModel):
    op: Literal["contains"]
    field: str
    value: str

    @staticmethod
    def contains(field: str, value: str) -> FieldFilter:
        """Match `field` containing `value`."""
        return FieldFilter(op="contains", field=field, value=value)


class Filter(BaseModel):
    op: Literal["and", "or"]
    filters: list[FieldFilter | Filter]

    @staticmethod
    def or_(*filters: FieldFilter | Filter) -> Filter:
        """Match any of `filters`."""
        return Filter(op="or", filters=list(filters))

    @staticmethod
    def and_(*filters: FieldFilter | Filter) -> Filter:
        """Match all of `filters`."""
        return Filter(op="and", filters=list(filters))


class SearchRequest(BaseModel):
    page_size: int
    query: str


class FilteredSearchRequest(SearchRequest):
    filters: Filter | None
    rank_profile: RankProfile | None = None

    @field_serializer("filters", when_used="unless-none")
    def _serialize_filters(self, filters: Filter) -> str:
        return filters.model_dump_json()


class DocumentsRequest(FilteredSearchRequest):
    msm: float


class PassagesWithinRequest(FilteredSearchRequest):
    document_ids: list[str] = Field(serialization_alias="document_id")
    msm: float


class SearchResponse[T](BaseModel):
    total_size: int | None
    results: list[T]
