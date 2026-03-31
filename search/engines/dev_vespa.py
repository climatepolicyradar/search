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

import json
import re
from typing import Any, Literal

import requests
from pydantic import AnyHttpUrl, BaseModel, TypeAdapter
from pydantic_settings import BaseSettings
from vespa.querybuilder import Grouping as G
from vespa.querybuilder.builder.builder import Q, QueryField

from search.data_in_models import Document, DocumentRelationship, LabelRelationship
from search.data_in_models import Label as DataInLabel
from search.engines import ListResponse, Pagination, SearchEngine
from search.label import Label
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


API_TIMEOUT = 5  # seconds
# We make this very obvious as it is used for values that should exist
MISSING_PLACEHOLDER = "MISSING"


# region Settings
class Settings(BaseSettings):
    vespa_endpoint: AnyHttpUrl
    vespa_read_token: str


# endregion


# region Filters
class LabelsCondition(BaseModel):
    field: Literal["labels.value.id"]
    op: Literal["contains", "not_contains"]
    value: str


class AttributesCondition(BaseModel):
    field: Literal[
        "attributes_string",
        "attributes_double",
        "attributes_boolean",
        "attributes_identifiers",
    ]
    key: str
    op: Literal["eq", "not_eq"]
    value: str | float | bool


Condition = LabelsCondition | AttributesCondition


class Filter(BaseModel):
    """A group of filters combined with AND or OR. Supports arbitrary nesting."""

    op: Literal["and", "or"]
    filters: list[Condition | Filter]


# Simple example: label contains "Romania"
SimpleExampleFilter = Filter(
    op="and",
    filters=[
        LabelsCondition(
            field="labels.value.id",
            op="contains",
            value="Romania",
        ),
    ],
)

# Complex example: ((label contains "Multilateral climate fund project" AND label contain "Principal") OR label contains "UN") AND label contains "Romania"
ComplexExampleFilter = Filter(
    op="and",
    filters=[
        Filter(
            op="or",
            filters=[
                Filter(
                    op="and",
                    filters=[
                        LabelsCondition(
                            field="labels.value.id",
                            op="contains",
                            value="Multilateral climate fund project",
                        ),
                        LabelsCondition(
                            field="labels.value.id",
                            op="contains",
                            value="Principal",
                        ),
                    ],
                ),
                LabelsCondition(
                    field="labels.value.id",
                    op="contains",
                    value="UN submissions",
                ),
            ],
        ),
        LabelsCondition(
            field="labels.value.id",
            op="contains",
            value="Romania",
        ),
        AttributesCondition(
            field="attributes_double",
            key="project_cost_usd",
            op="eq",
            value=1000000.0,
        ),
    ],
)


def _format_value(value: str | float | bool) -> str:
    """Format a value for YQL: strings get quotes, numbers do not, bools become 1/0 (byte)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


def _build_condition_yql(condition: Condition) -> str:
    match condition:
        case AttributesCondition():
            # Using `sameElement`, string fields use `contains`
            # while numeric/bool fields use comparison operators.
            # @see: https://docs.vespa.ai/en/querying/query-language.html#map
            value = condition.value
            if isinstance(value, str):
                inner = f'key contains "{condition.key}", value contains "{value}"'
            else:
                inner = (
                    f'key contains "{condition.key}", value = {_format_value(value)}'
                )
            expr = f"{condition.field} contains sameElement({inner})"
            if condition.op == "not_eq":
                return f"!({expr})"
            return expr

        case LabelsCondition():
            value = condition.value
            labels_expr = f'labels.value contains "{value}"'
            concepts_expr = f'concepts.value contains "{value}"'
            if condition.op == "not_contains":
                return f"!({labels_expr} or {concepts_expr})"
            return f"({labels_expr} or {concepts_expr})"


def _build_filter_yql(filter_group: Filter) -> str:
    """Recursively build YQL for a filter group."""
    parts: list[str] = []

    for item in filter_group.filters:
        if isinstance(item, Filter):
            # Recurse into nested group
            parts.append(_build_filter_yql(item))
        else:
            # It's a Condition
            parts.append(_build_condition_yql(item))

    if not parts:
        return ""

    join_op = f" {filter_group.op} "
    joined = join_op.join(parts)

    # Wrap in parentheses if multiple parts
    return f"({joined})" if len(parts) > 1 else joined


def _build_filter_query(filter_group: Filter | None) -> str:
    """Build the WHERE clause from a filter group."""
    if filter_group is None:
        return ""
    yql = _build_filter_yql(filter_group)
    return f" and {yql}" if yql else ""


# endregion Filters

# region Aggregations


class CountAggregation[T](BaseModel):
    count: int
    value: T


# endregion Aggregations


def _get_total_count(res: dict[str, Any]) -> int | None:
    return res.get("root", {}).get("fields", {}).get("totalCount")


class DevVespaDocumentSearchEngine(SearchEngine[Document]):
    """
    Search engine for dev Vespa

    This class should be using the Vespa Client, but we are having problems connecting to the remote server
    because of the way API Gateway handles trailing slashes.

    i.e.
    VespaClient connects to `/search/`.
    This isn't a viable URL for API Gatewayway, you can use
    - `/search`
    - `/search/{proxy+}`

    The secondary URL uses a `+` which matches 1 or more characters. 🤷

    For now we just use `requests` which yields the same results.
    """

    model_class = Document

    def __init__(
        self, settings: Settings, debug: bool = False, bolding: bool = False
    ) -> None:
        """
        Initialise the search engine.

        :param debug: When ``True``, request the ``debug-summary`` document
            summary from Vespa and store per-hit token information in
            :attr:`last_debug_info`.
        :param bolding: When ``False``, request the ``no-bolding`` document
            summary, returning plain title/description without ``<hi>`` tags.
            Ignored when ``debug=True``.
        """
        self.debug = debug
        self.bolding = bolding
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings

    _userQuery: str = (
        " and (userQuery() "
        # As geographies and title_synonyms use different Lucene analyzers
        # to the default fieldset, they're referenced explicitly in the query
        # so they can be searched.
        # https://docs.vespa.ai/en/reference/querying/yql.html#defaultindex
        ' or ({defaultIndex: "geographies"}userInput(@query))'
        ' or ({defaultIndex: "title_synonyms"}userInput(@query)))'
    )

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        filters_json_string: str | None = None,
    ) -> ListResponse[Document]:
        """Fetch a list of relevant search results."""

        where = "true "

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(filters)

        yql = f"select * from sources documents where {where}"
        if query:
            yql += self._userQuery
        logger.info(f"searching for yql: {yql}")

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": "nativerank",
        }
        if self.debug:
            request_body["presentation.summary"] = "debug-summary"
        if not self.bolding:
            request_body["presentation.bolding"] = "false"

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json=request_body,
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa query failed")
            return ListResponse(results=[], total_size=None, next_page_token=None)

        res = res.json()
        documents = []
        debug_info: list[dict[str, Any]] = []

        for hit in res.get("root").get("children", []):
            fields = hit.get("fields", {})
            # Map fields. Note: schema only has title, description.
            # source_url and original_document_id are required by Document.
            # We'll use the doc id for original_document_id and a dummy/empty source_url if missing.
            try:
                source = json.loads(fields.get("document_source"))
            except Exception:
                logger.warning(f"Document source is missing for {hit.get('id')}")
                continue
            labels: list[LabelRelationship] = []
            for label in source.get("labels", []):
                labels.append(
                    LabelRelationship(
                        type=label.get("type", MISSING_PLACEHOLDER),
                        value=DataInLabel(
                            id=label.get("value").get("id", MISSING_PLACEHOLDER),
                            value=label.get("value").get("value", MISSING_PLACEHOLDER),
                            type=label.get("value").get("type", MISSING_PLACEHOLDER),
                        ),
                        timestamp=label.get("timestamp"),
                    )
                )

            for concept in fields.get("concepts", []):
                labels.append(
                    LabelRelationship(
                        type="concept",
                        value=DataInLabel(
                            id=concept.get("id", MISSING_PLACEHOLDER),
                            type="concept",
                            value=concept.get("value", MISSING_PLACEHOLDER),
                        ),
                        passages_id=concept.get("passages_id", MISSING_PLACEHOLDER),
                        count=concept.get("count", MISSING_PLACEHOLDER),
                    )
                )

            document_relationships = TypeAdapter(
                list[DocumentRelationship]
            ).validate_python(source.get("documents", []))

            documents.append(
                Document(
                    id=source.get("id", MISSING_PLACEHOLDER),
                    title=fields.get("title", MISSING_PLACEHOLDER),
                    description=fields.get("description", MISSING_PLACEHOLDER),
                    labels=labels,
                    attributes=source.get("attributes", {}),
                    documents=document_relationships,
                )
            )

            if self.debug:
                # NOTE: these are all fields that are stored as type summary in the index.
                # This is because overriding the default summary in the schema adds fields
                # to it, rather than redefining the schema from scratch.
                _STANDARD_FIELDS = {
                    "document_source",
                    "sddocname",
                    "documentid",
                    "summaryfeatures",
                    "title",
                    "description",
                    "labels",
                }
                hit_debug = {
                    k: v for k, v in fields.items() if k not in _STANDARD_FIELDS
                }
                hit_debug["relevance"] = hit.get("relevance")
                hit_debug["summaryfeatures"] = fields.get("summaryfeatures")
                debug_info.append(hit_debug)

        self.last_debug_info = debug_info
        if self.debug and debug_info:
            logger.info(
                "Debug info for %d hits:\n%s",
                len(debug_info),
                json.dumps(debug_info, indent=2),
            )

        total_size = _get_total_count(res)
        return ListResponse(
            results=documents, total_size=total_size, next_page_token=None
        )

    def aggregations(
        self,
        query: str | None,
        filters_json_string: str | None = None,
    ) -> list[CountAggregation[Label]]:
        """Return aggregations (label/concept groups with counts) filtered by the search query."""
        # Build the top-level where clause from the search query and any filters,
        # mirroring how `search()` constructs its YQL.
        where = "true"
        if query:
            where += self._userQuery

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(filters)

        # Group labels and concepts across all documents matching the search query.
        # The top-level `where` already scopes the document set.
        # per-bucket filtering is not needed here.
        grouping = G.all(
            G.all(
                G.group("labels_type_value_attribute"),
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
            G.all(
                G.group("concepts_type_value_attribute"),
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
        )

        # Build a raw YQL string, the same way `search()` does, because the query
        # builder's `.where()` only accepts Condition/bool objects, not raw strings.
        select_fields = "labels_type_value_attribute, concepts_type_value_attribute"
        groupby_str = str(grouping)
        yql = f"select {select_fields} from documents where {where} | {groupby_str}"

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "query": query,
                    "hits": 0,
                    "timeout": "5s",
                    "model.language": "en",
                    "ranking.profile": "nativerank",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa aggregations query failed")
            return []

        root = res.json().get("root", {})
        root_children: list[dict] = root.get("children") or []
        groups: list[dict] = (
            root_children[0].get("children", []) if root_children else []
        )

        group_values = []
        for group in groups:
            group_values.extend(group.get("children", []))

        count_aggregations: list[CountAggregation[Label]] = []
        for group_value in group_values:
            label_type_value = group_value.get("value", "")
            label_type, _, label_value = label_type_value.partition("::")
            count_aggregations.append(
                CountAggregation(
                    count=group_value.get("fields", {}).get("count()", 0),
                    value=Label(
                        id=label_type_value,
                        value=label_value,
                        type=label_type or MISSING_PLACEHOLDER,
                    ),
                )
            )
        return count_aggregations

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()


class DevVespaPassageSearchEngine(SearchEngine[Passage]):
    """Search engine for passages in dev Vespa."""

    model_class = Passage

    def __init__(self, settings: Settings, debug: bool = False) -> None:
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        filters_json_string: str | None = None,  # noqa: ARG002
    ) -> ListResponse[Passage]:
        """Fetch a list of relevant passage search results."""
        yql = "select * from sources passages where true"
        if query:
            yql += " and userQuery()"

        logger.info(f"searching passages for yql: {yql}")

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
        }
        if self.debug:
            request_body["ranking.profile"] = "nativerank"
            request_body["presentation.summary"] = "debug-summary"

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json=request_body,
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa passages query failed")
            return ListResponse(results=[], total_size=None, next_page_token=None)

        res = res.json()
        passages: list[Passage] = []
        debug_info: list[dict[str, Any]] = []

        for hit in res.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            passages.append(
                Passage(
                    text_block_id=fields.get("id", ""),
                    text=fields.get("text", ""),
                    language=fields.get("language", ""),
                    type=fields.get("type", ""),
                    type_confidence=fields.get("type_confidence", 0.0),
                    page_number=fields.get("page_number", 0),
                    heading_id=fields.get("heading_id"),
                    document_id=fields.get("document_id", ""),
                )
            )
            if self.debug:
                debug_info.append(
                    {
                        "relevance": hit.get("relevance"),
                        "summaryfeatures": fields.get("summaryfeatures"),
                        "text_tokens": fields.get("text_tokens"),
                    }
                )

        self.last_debug_info = debug_info

        total_size = _get_total_count(res)
        return ListResponse(
            results=passages, total_size=total_size, next_page_token=None
        )

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()


class DevVespaLabelSearchEngine(SearchEngine[Label]):
    """Search engine for labels in dev Vespa."""

    model_class = Label

    def __init__(self, settings: Settings, debug: bool = False) -> None:
        self.debug = debug
        self.last_debug_info: list[dict[str, Any]] = []
        self.settings = settings

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        filters_json_string: str | None = None,  # noqa: ARG002
        label_type: str | None = None,
    ) -> ListResponse[Label]:
        """Fetch a list of relevant label search results."""
        yql = "select * from sources labels where true"
        if query:
            yql += " and userQuery()"
        if label_type:
            yql += f' and type contains "{label_type}"'

        logger.info(f"searching labels for yql: {yql}")

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": "nativerank",
        }

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json=request_body,
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa labels query failed")
            return ListResponse(results=[], total_size=None, next_page_token=None)

        res = res.json()
        labels: list[Label] = []
        debug_info: list[dict[str, Any]] = []

        for hit in res.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            labels.append(
                Label(
                    id=fields.get("id", ""),
                    type=fields.get("type", ""),
                    value=fields.get("value", ""),
                )
            )
            if self.debug:
                debug_info.append(
                    {
                        "relevance": hit.get("relevance"),
                        "summaryfeatures": fields.get("summaryfeatures"),
                        "value": fields.get("value", ""),
                        "alternative_labels": fields.get("alternative_labels", []),
                        "description": fields.get("description", ""),
                    }
                )

        self.last_debug_info = debug_info
        total_size = _get_total_count(res)
        return ListResponse(results=labels, total_size=total_size, next_page_token=None)

    def all_label_types(self) -> list[str]:
        """Fetch all distinct label types from the labels source."""
        yql = (
            "select * from sources labels where true "
            "| all(group(type) order(-count()) each(output(count())))"
        )

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "hits": 0,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa all_label_types query failed")
            return []

        res = res.json()
        types: list[str] = []

        root = res.get("root", {})
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

    def count(self, query: str) -> int:
        """Return hit count for DevVespaLabelSearchEngine."""
        raise NotImplementedError()


class DevVespaLabelTypeaheadSearchEngine(SearchEngine[Label]):
    """Typeahead search engine for labels, using grouping on the documents source."""

    model_class = Label

    def __init__(self, settings: Settings):
        self.settings = settings

    def search(
        self,
        query: str | None,
        pagination: Pagination,  # noqa: ARG002
        filters_json_string: str | None = None,  # noqa: ARG002
        label_type: str | None = None,
    ) -> ListResponse[Label]:
        """Returns unique values for concepts and labels in the documents"""
        labels_field = QueryField("labels_type_value_attribute")
        concepts_field = QueryField("concepts_type_value_attribute")

        safe_terms = re.escape(query) if query else "[^:]*"
        safe_label_type = re.escape(label_type) if label_type else "[^:]*"
        doc_regex = f"(?i)^{safe_label_type}::.*{safe_terms}.*"

        # Filter the documents that only have matching labels or concepts
        where = labels_field.matches(doc_regex) | concepts_field.matches(doc_regex)

        # Create the two groups, filtered and ordered
        grouping = G.all(
            G.all(
                G.group("labels_type_value_attribute"),
                f'filter(regex("{doc_regex}", labels_type_value_attribute))',
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
            G.all(
                G.group("concepts_type_value_attribute"),
                f'filter(regex("{doc_regex}", concepts_type_value_attribute))',
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
        )

        # Generate the YQL query
        yql = (
            Q.select(["labels_type_value_attribute", "concepts_type_value_attribute"])
            .from_("documents")
            .where(where)
            .groupby(grouping)
            .build()
        )

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "query": query,
                    # standard practice is "hits": 0 to get only aggregation if possible
                    "hits": 0,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa query failed")
            return ListResponse(results=[], total_size=None, next_page_token=None)

        # Parse the groups & transform => Labels
        # You can read more about grouping @see: https://docs.vespa.ai/en/querying/grouping.html
        # And there is an example of the response type @see: https://docs.vespa.ai/en/querying/grouping.html#pagination
        # I do wish this was typed
        root = res.json().get("root", {})
        groups = root.get("children", [{}])[0].get("children", [])

        group_values = []
        for group in groups:
            group_values.extend(group.get("children", []))

        labels: list[Label] = []
        for group_value in group_values:
            label_type_value = group_value.get("value", "")
            label_type, _, label_value = label_type_value.partition("::")
            labels.append(
                Label(
                    id=label_type_value,
                    value=label_value,
                    type=label_type or MISSING_PLACEHOLDER,
                )
            )
        return ListResponse(
            results=labels, total_size=len(labels), next_page_token=None
        )

    def all_label_types(self) -> list[str]:
        """Fetch all distinct label types (unfiltered)."""
        yql = (
            "select * from sources documents where true "
            "| all(group(labels_type_attribute) "
            "order(-count()) each(output(count())))"
        )

        try:
            res = requests.post(
                f"{self.settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "hits": 0,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa all_label_types query failed")
            return []

        res = res.json()
        types: list[str] = []

        root = res.get("root", {})
        children = root.get("children", [{}])[0].get("children", [])
        group_list = next(
            (
                item.get("children", [])
                for item in children
                if item.get("label") == "labels_type_attribute"
            ),
            [],
        )

        for group in group_list:
            types.append(group.get("value", ""))

        return types

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()
