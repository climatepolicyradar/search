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
from typing import Any, Literal

import requests
from pydantic import AnyHttpUrl, BaseModel, TypeAdapter
from pydantic_settings import BaseSettings
from vespa.querybuilder import Grouping as G

from search.data_in_models import Document, DocumentRelationship, LabelRelationship
from search.data_in_models import Label as DataInLabel
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.label import Label
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


API_TIMEOUT = 5  # seconds
HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS = 512
# We make this very obvious as it is used for values that should exist
MISSING_PLACEHOLDER = "MISSING"


# region Settings
class Settings(BaseSettings):
    vespa_endpoint: AnyHttpUrl
    vespa_read_token: str


# endregion


# region Filters
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


class FieldFilter(BaseModel):
    field: str
    op: Literal["contains", "not_contains"]
    value: str


Condition = AttributesCondition | FieldFilter


class Filter(BaseModel):
    """A group of filters combined with AND or OR. Supports arbitrary nesting."""

    op: Literal["and", "or"]
    filters: list[Condition | Filter]


# Simple example: label contains "Romania"
SimpleExampleFilter = Filter(
    op="and",
    filters=[
        FieldFilter(
            field="labels.value.value",
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
                        FieldFilter(
                            field="labels.value.value",
                            op="contains",
                            value="Multilateral climate fund project",
                        ),
                        FieldFilter(
                            field="labels.value.value",
                            op="contains",
                            value="Principal",
                        ),
                    ],
                ),
                FieldFilter(
                    field="labels.value.value",
                    op="contains",
                    value="UN submissions",
                ),
            ],
        ),
        FieldFilter(
            field="labels.value.value",
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


filter_field_to_vespa_field_map = {
    "labels.value.id": ["labels.id", "concepts.id"],
    "labels.value.value": ["labels.value", "concepts.value"],
}

sort_field_to_vespa_field_map = {
    "attributes.published_date": ["attributes_published_date"],
    "title": ["title_sort"],
}

# Public API field names for ``order_by`` (JSON paths + ``relevance``), aligned
# with :data:`sort_field_to_vespa_field_map` keys.
DOCUMENT_SORT_API_FIELDS: frozenset[str] = frozenset(
    {"relevance", *sort_field_to_vespa_field_map.keys()}
)


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

        case FieldFilter():
            fields = filter_field_to_vespa_field_map.get(
                condition.field, [condition.field]
            )
            value = _format_value(condition.value)
            exprs = [f"{field} contains {value}" for field in fields]
            combined = " or ".join(exprs)
            if condition.op == "not_contains":
                return f"!({combined})"
            return f"({combined})" if len(exprs) > 1 else combined


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

# region Document sort (Vespa ranking.sorting)


def _document_sort_ranking_string(vespa_attr: str, direction: str) -> str:
    """
    Build Vespa ``ranking.sorting`` for a document sort attribute.

    :param vespa_attr: First mapped field name from
        :data:`sort_field_to_vespa_field_map`
    :type vespa_attr: str
    :param direction: ``asc`` or ``desc``
    :type direction: str
    :return: Vespa sorting expression fragment
    :rtype: str
    :raises AssertionError: if ``vespa_attr`` is not handled
    """
    if vespa_attr == "attributes_published_date":
        if direction == "desc":
            return "-attributes_published_date"
        return "+missing(attributes_published_date,last) +attributes_published_date"
    if vespa_attr == "title_sort":
        sign = "+" if direction == "asc" else "-"
        return f"{sign}{vespa_attr}"
    raise AssertionError(f"unexpected Vespa sort attribute {vespa_attr!r}")


def _ranking_overrides_for_document_order_by(
    order_by: list[OrderBy],
) -> dict[str, Any]:
    """
    Translate ``order_by`` clauses into Vespa ranking request fields.

    Only the first clause is applied (multilevel sorts can be added later).
    ``relevance`` keeps default ``nativerank`` ordering (no ``ranking.sorting``).

    :param order_by: Parsed ``<field> <direction>`` clauses (public JSON paths
        such as ``attributes.published_date`` and ``title``, plus ``relevance``)
    :type order_by: list[OrderBy]
    :return: Key/value fragments to merge into the Vespa JSON body
    :rtype: dict[str, Any]
    :raises ValueError: if the field is not supported for documents
    """
    if not order_by:
        return {}
    primary = order_by[0]
    if primary.field not in DOCUMENT_SORT_API_FIELDS:
        raise ValueError(
            f"order_by field {primary.field!r} is not supported for documents; "
            f"expected one of: {sorted(DOCUMENT_SORT_API_FIELDS)}"
        )
    if primary.direction not in ("asc", "desc"):
        raise ValueError(
            f"invalid order direction {primary.direction!r}; use asc or desc"
        )
    if primary.field == "relevance":
        if primary.direction == "asc":
            logger.warning(
                "relevance ascending is not supported; using relevance (desc) ordering"
            )
        return {}

    # ``DOCUMENT_SORT_API_FIELDS`` is ``relevance`` plus map keys, so this
    # lookup is always valid here.
    vespa_attr = sort_field_to_vespa_field_map[primary.field][0]
    sorting = _document_sort_ranking_string(vespa_attr, primary.direction)
    return {
        "ranking.profile": "unranked",
        "ranking.sorting": sorting,
        # Match date sorts: degrading can skew ordering for fast-search attrs.
        "sorting.degrading": False,
    }


# endregion Document sort

# region Aggregations


class CountAggregation[T](BaseModel):
    count: int
    value: T


# endregion Aggregations


def _get_total_count(response: dict[str, Any]) -> int | None:
    return response.get("root", {}).get("fields", {}).get("totalCount")


def _execute_vespa_query(
    *,
    endpoint: str,
    token: str,
    request_body: dict[str, Any],
    request_context: str,
    post_fn=requests.post,
) -> dict[str, Any] | None:
    """
    Execute a Vespa query and emit contextual logs.

    :param endpoint: Fully-qualified Vespa query endpoint URL.
    :type endpoint: str
    :param token: Bearer token used for read access.
    :type token: str
    :param request_body: JSON payload sent to Vespa.
    :type request_body: dict[str, Any]
    :param request_context: Context label for logs.
    :type request_context: str
    :param post_fn: HTTP post callable for dependency injection in tests.
    :type post_fn: typing.Callable[..., requests.Response]
    :return: Decoded JSON response when successful, else ``None``.
    :rtype: dict[str, Any] | None
    """
    logger.info("Vespa request started [%s]", request_context)
    logger.debug(
        "Vespa request payload [%s]: %s",
        request_context,
        json.dumps(request_body, indent=2),
    )

    try:
        response = post_fn(
            endpoint,
            json=request_body,
            timeout=API_TIMEOUT,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
    except Exception:
        logger.exception(
            "Error: Vespa request failed before a response was received [%s]",
            request_context,
        )
        return None

    if response.status_code >= 400:
        body_preview = (response.text or "")[:HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS]
        logger.error(
            "Error: Vespa returned a non-success status code [%s] "
            "(status=%s, body_preview=%r)",
            request_context,
            response.status_code,
            body_preview,
        )
        return None

    try:
        response_json = response.json()
    except ValueError:
        logger.exception("Error: Vespa returned invalid JSON [%s]", request_context)
        return None

    hit_count = len(response_json.get("root", {}).get("children", []) or [])
    logger.info(
        "Success: Vespa request completed [%s] (hits=%s, total_count=%s)",
        request_context,
        hit_count,
        _get_total_count(response_json),
    )
    return response_json


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
        ' or ({defaultIndex: "title_synonyms"}userInput(@query))'
        ' or ({defaultIndex: "identifiers"}userInput(@query)))'
    )

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
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
        logger.info("🔎 Document search query built (query=%r, yql=%s)", query, yql)

        sort_overrides = _ranking_overrides_for_document_order_by(order_by)

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            # This should be set at the Vespa app level, but is not working for some reason
            # FIXME: Fix this 👆
            "maxHits": 50000,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": "nativerank",
        }
        request_body.update(sort_overrides)

        if self.debug:
            request_body["presentation.summary"] = "debug-summary"
        if not self.bolding:
            request_body["presentation.bolding"] = "false"

        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="documents.search",
        )
        if response is None:
            return ListResponse(results=[], total_size=None, next_page_token=None)
        documents = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            # Map fields. Note: schema only has title, description.
            # source_url and original_document_id are required by Document.
            # We'll use the doc id for original_document_id and a dummy/empty source_url if missing.
            try:
                source = json.loads(fields.get("document_source"))
            except Exception:
                logger.warning(
                    "Document source could not be parsed for hit id=%r",
                    hit.get("id"),
                )
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

            # `passages` and `passages_text` indices are aligned
            # as `passages_text` is derived from `passages` in the schema.
            # Vespa wraps matched terms with <hi>...</hi> on the bolded `passages_text` field.
            # We use this to identify which `passages[i]` matched the query.
            document_id = source.get("id", MISSING_PLACEHOLDER)
            passages_field = fields.get("passages", [])
            passages_text = fields.get("passages_text", [])
            passages: list[Passage] = []
            for i, passage in enumerate(passages_field):
                if i >= len(passages_text):
                    break
                bolded_text = passages_text[i]
                if "<hi>" not in bolded_text:
                    continue
                passages.append(
                    Passage(
                        text_block_id=passage.get("text_block_id", ""),
                        text=bolded_text,
                        language=passage.get("language", ""),
                        type=passage.get("type", ""),
                        type_confidence=passage.get("type_confidence", 0.0),
                        page_number=passage.get("page_number", 0),
                        heading_id=passage.get("heading_id"),
                        document_id=document_id,
                    )
                )

            documents.append(
                Document(
                    id=source.get("id", MISSING_PLACEHOLDER),
                    title=fields.get("title", MISSING_PLACEHOLDER),
                    description=fields.get("description", MISSING_PLACEHOLDER),
                    labels=labels,
                    attributes=source.get("attributes", {}),
                    documents=document_relationships,
                    passages=passages,
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
                "Debug info for %d document hits:\n%s",
                len(debug_info),
                json.dumps(debug_info, indent=2),
            )

        total_size = _get_total_count(response)
        return ListResponse(
            results=documents, total_size=total_size, next_page_token=None
        )

    @staticmethod
    def parse_label_type_id_value(s: str) -> tuple[str, str, str]:
        """
        Parse a `{type}::{id}::{value}` string into its three components.

        {id} may contain `::`
        e.g: `geography::geography::USA::United States of America`
        """
        label_type, _, label_id_value = s.partition("::")
        label_id, _, label_value = label_id_value.rpartition("::")
        return label_type, label_id, label_value

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
                G.group("labels_type_id_value_attribute"),
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
            G.all(
                G.group("concepts_type_id_value_attribute"),
                # This is the max we expect to see
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            ),
        )

        # Build a raw YQL string, the same way `search()` does, because the query
        # builder's `.where()` only accepts Condition/bool objects, not raw strings.
        select_fields = (
            "labels_type_id_value_attribute, concepts_type_id_value_attribute"
        )
        groupby_str = str(grouping)
        yql = f"select {select_fields} from documents where {where} | {groupby_str}"

        request_body = {
            "yql": yql,
            "query": query,
            "hits": 0,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": "nativerank",
        }
        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="documents.aggregations",
        )
        if response is None:
            return []

        root = response.get("root", {})
        root_children: list[dict] = root.get("children") or []
        groups: list[dict] = (
            root_children[0].get("children", []) if root_children else []
        )

        group_values = []
        for group in groups:
            group_values.extend(group.get("children", []))

        count_aggregations: list[CountAggregation[Label]] = []
        for group_value in group_values:
            label_type_id_value = group_value.get("value", "")
            label_type, label_id, label_value = self.parse_label_type_id_value(
                label_type_id_value
            )
            count_aggregations.append(
                CountAggregation(
                    count=group_value.get("fields", {}).get("count()", 0),
                    value=Label(
                        id=label_id,
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
        order_by: list[OrderBy],  # noqa: ARG002
        filters_json_string: str | None = None,  # noqa: ARG002
    ) -> ListResponse[Passage]:
        """Fetch a list of relevant passage search results."""
        yql = "select * from sources passages where true"
        if query:
            yql += " and userQuery()"

        logger.info("🔎 Passage search query built (query=%r, yql=%s)", query, yql)

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

        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="passages.search",
        )
        if response is None:
            return ListResponse(results=[], total_size=None, next_page_token=None)
        passages: list[Passage] = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
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

        total_size = _get_total_count(response)
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
        order_by: list[OrderBy],  # noqa: ARG002
        filters_json_string: str | None = None,  # noqa: ARG002
        label_type: str | None = None,
    ) -> ListResponse[Label]:
        """Fetch a list of relevant label search results."""

        where = " true "

        if filters_json_string:
            filters = Filter.model_validate_json(filters_json_string)
            where += _build_filter_query(filters)

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
            # This should be set at the Vespa app level, but is not working for some reason
            # FIXME: Fix this 👆
            "maxHits": 50000,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            "ranking.profile": "nativerank",
            "rules.rulebase": "labels",
        }

        response = _execute_vespa_query(
            endpoint=f"{self.settings.vespa_endpoint}/search",
            token=self.settings.vespa_read_token,
            request_body=request_body,
            request_context="labels.search",
        )
        if response is None:
            return ListResponse(results=[], total_size=None, next_page_token=None)
        labels: list[Label] = []
        debug_info: list[dict[str, Any]] = []

        for hit in response.get("root", {}).get("children", []):
            fields = hit.get("fields", {})
            alternative_labels = fields.get("alternative_labels", [])
            if not isinstance(alternative_labels, list):
                alternative_labels = []
            subconcept_labels = fields.get("subconcept_labels", [])
            if not isinstance(subconcept_labels, list):
                subconcept_labels = []
            labels.append(
                Label(
                    id=fields.get("id", ""),
                    type=fields.get("type", ""),
                    value=fields.get("value", ""),
                    alternative_labels=alternative_labels,
                    subconcept_labels=subconcept_labels,
                    description=fields.get("description", ""),
                )
            )
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
        if response is None:
            return []
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

    def count(self, query: str) -> int:
        """Return hit count for DevVespaLabelSearchEngine."""
        raise NotImplementedError()
