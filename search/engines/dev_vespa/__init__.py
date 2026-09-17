"""
Dev vespa API

Should be using the Vespa Client, but we are having problems
connecting to the remote server because of the way API Gateway
handles trailing slashes.

i.e.
VespaClient connects to `/search/`.
This isn't a viable URL for API Gatewayway, you can use
- `/search`
- `/search/{proxy+}`

The secondary URL uses a `+` which matches 1 or more characters. 🤷

For now we just use `requests` which yields the same results.
"""

from __future__ import annotations

from typing import Any

from search.data_in_models import LabelRelationship
from search.data_in_models import Label as DataInLabel
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.engines.dev_vespa.documents_search_engine import (
    DevVespaDocumentSearchEngine,
    DevVespaPrincipalDocumentSearchEngine,
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    _DEFAULT_DOCUMENT_TOTAL_TARGET_HITS,
    _DEFAULT_PASSAGES_BREADTH_WEIGHT,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)
from search.engines.dev_vespa.labels import (
    MISSING_PLACEHOLDER,
    CountAggregation,
    DevVespaInstanceAddIn,
    get_labels_from_vespa_response,
)
from search.engines.vespa_query.filters import (
    ArrayStructField,
    AttributesCondition,
    ComplexExampleFilter,
    Condition,
    FieldFilter,
    Filter,
    SimpleExampleFilter,
    TOPIC_FILTER_FIELD,
    TOPIC_ID_PREFIX,
    _build_condition_yql,
    _build_filter_query,
    _build_filter_yql,
    _facet_filter_label_type,
    _format_value,
    _get_label_types_from_filters,
    _prune_filter,
    _published_date_operand,
    _to_unix_timestamp,
    _topic_ids_from_filters,
    _value_type_to_vespa_attributes_field,
    normalise_topic_id,
)
from search.engines.vespa_query.query_text import (
    CURRENCY_SYMBOL_REPLACEMENTS,
    GEOGRAPHY_ALIASES,
    _fold_accents,
    _normalize_currency_symbols,
    _resolve_geography_aliases,
    _strip_quotes,
)
from search.engines.vespa_query.client import (
    API_TIMEOUT,
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,
    Settings,
    _execute_vespa_query,
    _get_total_count,
    _warn_if_degraded,
)
from search.engines.vespa_query.sorting import (
    DOCUMENT_SORT_API_FIELDS,
    PASSAGE_SORT_API_FIELDS,
    _document_sort_ranking_string,
    _passage_sort_ranking_string,
    _ranking_overrides_for_document_order_by,
    _ranking_overrides_for_passage_order_by,
    passage_sort_field_to_vespa_field_map,
    sort_field_to_vespa_field_map,
)
from search.label import Label
from search.log import get_logger
from search.passage import Passage
from search.vespa.passage import VespaPassage

logger = get_logger(__name__)


# region Documents
_DEFAULT_TOPIC_WEIGHT = 1.0


passages_filter_field_to_vespa_field_map: dict[str, list[str]] = {
    "document_id": ["document_id"],
    "principal_id": ["principal_id"],
}
passages_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {
    "labels.value.id": ArrayStructField("labels", "id"),
    "labels.value.value": ArrayStructField("labels", "value"),
    "labels.value.type": ArrayStructField("labels", "type"),
}


_DEFAULT_PASSAGE_RANK_PROFILE = "bm25_multiplicative"


class DevVespaPassageSearchEngine(DevVespaInstanceAddIn, SearchEngine[Passage]):
    """Search engine for passages in dev Vespa."""

    model_class = Passage

    def __init__(
        self,
        settings: Settings,
        debug: bool = False,
        ranking_profile: str = _DEFAULT_PASSAGE_RANK_PROFILE,
        topic_weight: float = _DEFAULT_TOPIC_WEIGHT,
    ) -> None:
        """Initialise the search engine."""
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings
        self.ranking_profile = ranking_profile
        self.topic_weight = topic_weight

    @property
    def parameters(self) -> dict[str, Any]:
        """Tuning parameters, surfaced in relevance-test logging."""
        return {
            "ranking_profile": self.ranking_profile,
            "topic_weight": self.topic_weight,
        }

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters_json_string: str | None = None,
        bolding: bool = False,
    ) -> ListResponse[Passage]:
        """Fetch a list of relevant passage search results."""
        if query:
            query = _strip_quotes(query)

        where = "true"
        filters: Filter | None = None

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(
                filters,
                field_map=passages_filter_field_to_vespa_field_map,
                struct_map=passages_filter_struct_field_to_vespa_field_map,
            )

        yql = f"select * from sources passages where {where}"
        if query:
            yql += " and userQuery()"

        logger.info("🔎 Passage search query built (query=%r, yql=%s)", query, yql)

        sort_overrides = _ranking_overrides_for_passage_order_by(order_by)

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": _normalize_currency_symbols(query) if query else query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "rules.rulebase": "passages",
            "presentation.summary": "debug-summary" if self.debug else "search",
            "ranking.profile": self.ranking_profile,
        }
        request_body.update(sort_overrides)

        topic_ids = _topic_ids_from_filters(filters)
        if topic_ids and not sort_overrides:
            request_body["input.query(topic_q)"] = dict.fromkeys(topic_ids, 1.0)
            request_body["input.query(topic_weight)"] = self.topic_weight

        # `passage.content` is `bolding: on` in the schema, so Vespa bolds by default -
        # it has to be turned off explicitly.
        if not bolding:
            request_body["presentation.bolding"] = "false"

        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="passages.search",
        )
        passages: list[Passage] = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            vespa_passage = VespaPassage.model_validate(fields)
            passages.append(Passage.from_vespa_passage(vespa_passage, bolding=bolding))
            if self.debug:
                debug_info.append(
                    {
                        "relevance": hit.get("relevance"),
                        "summaryfeatures": fields.get("summaryfeatures"),
                        "text_tokens": fields.get("text_tokens"),
                    }
                )

        self.last_debug_info = debug_info

        total_size = _get_total_count(response)
        return ListResponse(
            results=passages, total_size=total_size, next_page_token=None
        )

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()


# region Labels


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
