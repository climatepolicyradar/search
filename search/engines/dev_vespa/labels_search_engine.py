"""The label search engine for dev Vespa."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx2
from opentelemetry import trace
from pydantic import ValidationError

from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.engines.dev_vespa.labels import DevVespaInstanceAddIn
from search.engines.vespa_query.client import (
    Settings,
    _get_total_count,
    aexecute_vespa_query,
)
from search.engines.vespa_query.filters import (
    ArrayStructField,
    Filter,
    _build_filter_query,
)
from search.engines.vespa_query.query_text_modifiers import _strip_quotes
from search.label import LabelSearchResult
from search.log import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

labels_filter_field_to_vespa_field_map: dict[str, list[str]] = {}
labels_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {
    "labels.type": ArrayStructField("labels", "relationship"),
    "labels.value.id": ArrayStructField("labels", "id"),
    "labels.value.value": ArrayStructField("labels", "value"),
    "labels.value.type": ArrayStructField("labels", "type"),
}

_ALL_LABELS_HITS = 10_000


def _label_from_hit(hit: dict[str, Any]) -> LabelSearchResult:
    fields = hit.get("fields", {})

    alternative_labels = fields.get("alternative_labels", [])
    if not isinstance(alternative_labels, list):
        alternative_labels = []

    return LabelSearchResult.model_validate(
        {
            "id": fields.get("id"),
            "type": fields.get("type"),
            "value": fields.get("value"),
            "alternative_labels": alternative_labels,
            "labels": [
                {
                    "type": relationship.get("relationship"),
                    "value": {
                        "id": relationship.get("id"),
                        "type": relationship.get("type"),
                        "value": relationship.get("value"),
                    },
                    "timestamp": relationship.get("timestamp"),
                }
                for relationship in fields.get("labels", [])
            ],
        }
    )


class LabelSearchEngine(Protocol):
    async def asearch(
            self,
            query: str | None,
            pagination: Pagination,
            order_by: list[OrderBy],
            filters: Filter | None = None,
            label_type: str | None = None,
        ) -> ListResponse[LabelSearchResult]:
        """Search labels."""
        ...

    async def all_labels(self) -> list[LabelSearchResult]:
        """Fetch every active label."""
        ...


class DevVespaLabelSearchEngine(DevVespaInstanceAddIn, SearchEngine[LabelSearchResult]):
    """Search engine for labels in dev Vespa."""

    model_class = LabelSearchResult

    def __init__(
        self, settings: Settings, httpx: httpx2.AsyncClient, debug: bool = False
    ) -> None:
        self._httpx = httpx
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters: Filter | None = None,
        label_type: str | None = None,
    ) -> ListResponse[LabelSearchResult]:
        """Fetch a list of relevant label search results."""
        return asyncio.run(
            self.asearch(
                query=query,
                pagination=pagination,
                order_by=order_by,
                filters=filters,
                label_type=label_type,
            )
        )

    async def asearch(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],  # noqa: ARG002
        filters: Filter | None = None,
        label_type: str | None = None,
    ) -> ListResponse[LabelSearchResult]:
        """Fetch a list of relevant label search results."""
        if query:
            query = _strip_quotes(query)

        where = ' status contains "active" '

        if filters is not None:
            where += _build_filter_query(
                filters,
                field_map=labels_filter_field_to_vespa_field_map,
                struct_map=labels_filter_struct_field_to_vespa_field_map,
            )

        yql = f"select * from sources labels where {where}"
        if query:
            # We prioritise prefix matches, but then search more loosely and rank them lower
            yql += (
                " and (value_attribute contains ({prefix: true, weight: 200}@query)"
                " or alternative_labels_attribute contains ({prefix: true, weight: 200}@query)"
                " or userQuery())"
            )
        if label_type:
            yql += f' and type contains "{label_type}"'

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": "nativerank",
            "rules.rulebase": "labels",
            "query_profile": "default",
        }

        response = await aexecute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="labels.search",
            client=self._httpx,
        )
        labels: list[LabelSearchResult] = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            try:
                label = _label_from_hit(hit)
            except ValidationError:
                logger.warning("Label fields are invalid for hit id=%r", hit.get("id"))
                continue

            labels.append(label)

            if self.debug:
                debug_info.append(
                    {
                        "relevance": hit.get("relevance"),
                        "summaryfeatures": fields.get("summaryfeatures"),
                        "value": fields.get("value", ""),
                        "alternative_labels": fields.get("alternative_labels", []),
                        "subconcept_labels": fields.get("subconcept_labels", []),
                        "description": fields.get("description", ""),
                    }
                )

        self.last_debug_info = debug_info
        total_size = _get_total_count(response)
        return ListResponse(results=labels, total_size=total_size, next_page_token=None)

    async def all_labels(self) -> list[LabelSearchResult]:
        """Fetch every active label, for callers that need the whole taxonomy."""
        with tracer.start_as_current_span("labels.all") as span:
            response = await aexecute_vespa_query(
                endpoint=f"{self.settings.vespa_endpoint}/search",
                token=self.settings.vespa_read_token,
                request_body={
                    "yql": 'select * from sources labels where status contains "active"',
                    "hits": _ALL_LABELS_HITS,
                    "ranking.profile": "unranked",
                    "query_profile": "default",
                },
                request_context="labels.all",
                client=self._httpx,
            )

            labels: list[LabelSearchResult] = []
            for hit in response.get("root", {}).get("children", []):
                try:
                    labels.append(_label_from_hit(hit))
                except ValidationError:
                    logger.warning(
                        "Label fields are invalid for hit id=%r", hit.get("id")
                    )

            span.set_attribute("labels.count", len(labels))
            span.set_attribute("labels.total", _get_total_count(response) or 0)
            return labels

    def count(self, query: str) -> int:
        """Return hit count for DevVespaLabelSearchEngine."""
        raise NotImplementedError()
