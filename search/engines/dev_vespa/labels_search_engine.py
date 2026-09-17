"""The label search engine for dev Vespa."""

from __future__ import annotations

from typing import Any

from search.data_in_models import Label as DataInLabel
from search.data_in_models import LabelRelationship
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.engines.dev_vespa.labels import DevVespaInstanceAddIn
from search.engines.vespa_query.client import (
    Settings,
    _execute_vespa_query,
    _get_total_count,
)
from search.engines.vespa_query.filters import (
    ArrayStructField,
    Filter,
    _build_filter_query,
)
from search.engines.vespa_query.query_text import _strip_quotes
from search.log import get_logger

logger = get_logger(__name__)

labels_filter_field_to_vespa_field_map: dict[str, list[str]] = {}
labels_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {
    "labels.type": ArrayStructField("labels", "relationship"),
    "labels.value.id": ArrayStructField("labels", "id"),
    "labels.value.value": ArrayStructField("labels", "value"),
    "labels.value.type": ArrayStructField("labels", "type"),
}


class DevVespaLabelSearchEngine(DevVespaInstanceAddIn, SearchEngine[DataInLabel]):
    """Search engine for labels in dev Vespa."""

    model_class = DataInLabel

    def __init__(self, settings: Settings, debug: bool = False) -> None:
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],  # noqa: ARG002
        filters_json_string: str | None = None,  # noqa: ARG002
        label_type: str | None = None,
    ) -> ListResponse[DataInLabel]:
        """Fetch a list of relevant label search results."""
        if query:
            query = _strip_quotes(query)

        where = " true "

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
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

        logger.info("🔎 Label search query built (query=%r, yql=%s)", query, yql)

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

        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="labels.search",
        )
        labels: list[DataInLabel] = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            alternative_labels = fields.get("alternative_labels", [])
            if not isinstance(alternative_labels, list):
                alternative_labels = []
            subconcept_labels = fields.get("subconcept_labels", [])
            if not isinstance(subconcept_labels, list):
                subconcept_labels = []

            label_source = fields.get("label_source", "")
            if (
                label_source is not None
                and isinstance(label_source, str)
                and label_source != ""
            ):
                try:
                    label = DataInLabel.model_validate_json(label_source)
                    labels.append(label)
                except Exception:
                    logger.warning(
                        "Label source is invalid for hit id=%r", hit.get("id")
                    )
                    continue
            else:
                logger.warning("Label source is empty for hit id=%r", hit.get("id"))
                continue

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

    def all_label_types(self) -> list[str]:
        """Fetch all distinct label types from the labels source."""
        yql = (
            "select * from sources labels where true "
            "| all(group(type) order(-count()) each(output(count())))"
        )

        request_body = {
            "yql": yql,
            "hits": 0,
            "timeout": "5s",
        }
        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="labels.all_label_types",
        )
        types: list[str] = []

        root = response.get("root", {})
        children = root.get("children", [{}])[0].get("children", [])
        group_list = next(
            (
                item.get("children", [])
                for item in children
                if item.get("label") == "type"
            ),
            [],
        )

        for group in group_list:
            types.append(group.get("value", ""))

        return types

    def tmp_labels(self) -> ListResponse[DataInLabel]:
        """Labels for UI testing"""
        return ListResponse(
            results=[
                DataInLabel(
                    id="region::South Asia",
                    type="region",
                    value="South Asia",
                    labels=[],
                ),
                DataInLabel(
                    id="country::India",
                    type="country",
                    value="India",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="region::South Asia",
                                type="region",
                                value="South Asia",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="subdivision::Kerela",
                    type="subdivision",
                    value="Kerela",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="country::India",
                                type="country",
                                value="India",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="subdivision::Punjab",
                    type="subdivision",
                    value="Punjab",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="country::India",
                                type="country",
                                value="India",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="region::North America",
                    type="region",
                    value="North America",
                    labels=[],
                ),
                DataInLabel(
                    id="country::USA",
                    type="country",
                    value="USA",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="region::North America",
                                type="region",
                                value="North America",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="country::Canada",
                    type="country",
                    value="Canada",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="region::North America",
                                type="region",
                                value="North America",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="subdivision::Texas",
                    type="subdivision",
                    value="Texas",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="country::USA",
                                type="country",
                                value="USA",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="subdivision::California",
                    type="subdivision",
                    value="California",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="country::USA",
                                type="country",
                                value="USA",
                            ),
                        ),
                    ],
                ),
                DataInLabel(
                    id="subdivision::British Columbia",
                    type="subdivision",
                    value="British Columbia",
                    labels=[
                        LabelRelationship(
                            type="subconcept_of",
                            value=DataInLabel(
                                id="country::Canada",
                                type="country",
                                value="Canada",
                            ),
                        ),
                    ],
                ),
            ],
            total_size=0,
            next_page_token=None,
        )

    def count(self, query: str) -> int:
        """Return hit count for DevVespaLabelSearchEngine."""
        raise NotImplementedError()
