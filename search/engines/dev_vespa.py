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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http import HTTPStatus
from typing import Any, Literal, NamedTuple

import requests
from pydantic import AnyHttpUrl, BaseModel, TypeAdapter
from pydantic_settings import BaseSettings
from vespa.querybuilder import Grouping as G

from search.data_in_models import Document, DocumentRelationship, LabelRelationship
from search.data_in_models import Label as DataInLabel
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine, VespaError
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
    vespa_dev_instance_name: str | None = (
        None  # personal dev instance; None == full/prod
    )


# endregion


# region Filters
class AttributesCondition(BaseModel):
    field: Literal[
        "attributes_string",
        "attributes_double",
        "attributes_boolean",
        "attributes_identifiers",
        "attributes.published_date",
    ]
    key: str
    op: Literal["eq", "not_eq", "lt", "lte", "gt", "gte"]
    value: str | int | float | bool


class FieldFilter(BaseModel):
    field: str
    op: Literal["contains", "not_contains"]
    value: str | float | bool


Condition = AttributesCondition | FieldFilter


class Filter(BaseModel):
    """A group of filters combined with AND or OR. Supports arbitrary nesting."""

    op: Literal["and", "or"]
    filters: list[Condition | Filter]


class ArrayStructField(NamedTuple):
    """Used to locate a subfield within a Vespa array-of-structs field."""

    array_field: str
    subfield: str


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


def _format_value(value: str | int | float | bool) -> str:
    """Format a value for YQL: strings get quotes, numbers do not, bools become 1/0 (byte)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


def _to_unix_timestamp(value: str) -> int:
    """Convert an ISO datetime string to Unix timestamp (seconds)."""
    normalised = value.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalised).timestamp())


def _published_date_operand(value: str | int | float, op: str) -> int:
    """
    Translate a published-date filter value into epoch seconds.

    ``attributes.published_date`` is stored as a scalar Unix timestamp in
    Vespa. The API normalises ISO datetime strings at the boundary, and we keep
    this fallback conversion here to preserve existing callers.
    """
    _ = op
    if isinstance(value, str):
        return _to_unix_timestamp(value)
    return int(value)


_value_type_to_vespa_attributes_field = {
    str: "attributes_string",
    float: "attributes_double",
    int: "attributes_double",
    bool: "attributes_boolean",
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


def _build_condition_yql(
    condition: Condition,
    field_map: dict[str, list[str]],
) -> str:
    match condition:
        case AttributesCondition():
            if condition.field == "attributes.published_date":
                vespa_field = sort_field_to_vespa_field_map.get(
                    condition.field, [condition.field]
                )[0]
                op_to_symbol = {
                    "eq": "=",
                    "lt": "<",
                    "lte": "<=",
                    "gt": ">",
                    "gte": ">=",
                }
                operand = _published_date_operand(condition.value, condition.op)
                if condition.op == "not_eq":
                    return f"!({vespa_field} = {operand})"
                op_symbol = op_to_symbol.get(condition.op)
                if op_symbol is None:
                    raise ValueError(
                        f"unsupported op={condition.op!r} for field={condition.field!r}"
                    )
                return f"{vespa_field} {op_symbol} {operand}"

            # Using `sameElement`, string fields use `contains`
            # while numeric/bool fields use comparison operators.
            # @see: https://docs.vespa.ai/en/querying/query-language.html#map
            value = condition.value
            if isinstance(value, str):
                if condition.op not in ("eq", "not_eq"):
                    raise ValueError(
                        f"string attributes only support eq/not_eq, got {condition.op!r}"
                    )
                inner = f'key contains "{condition.key}", value contains "{value}"'
            else:
                op_to_symbol = {
                    "eq": "=",
                    "not_eq": "=",
                    "lt": "<",
                    "lte": "<=",
                    "gt": ">",
                    "gte": ">=",
                }
                op_symbol = op_to_symbol.get(condition.op)
                if op_symbol is None:
                    raise ValueError(
                        f"unsupported op={condition.op!r} for field={condition.field!r}"
                    )
                inner = f'key contains "{condition.key}", value {op_symbol} {_format_value(value)}'
            expr = f"{condition.field} contains sameElement({inner})"
            if condition.op == "not_eq":
                return f"!({expr})"
            return expr

        case FieldFilter() if condition.field.startswith("attributes."):
            key = condition.field.split(".", 1)[1]
            vespa_field = _value_type_to_vespa_attributes_field[type(condition.value)]
            # we need to use `contains` on strings
            if isinstance(condition.value, str):
                inner = f'key contains "{key}", value contains "{condition.value}"'
            # and operators e.g. `=` on numerics & bools
            else:
                inner = (
                    f'key contains "{key}", value = {_format_value(condition.value)}'
                )
            expr = f"{vespa_field} contains sameElement({inner})"
            if condition.op == "not_contains":
                return f"!({expr})"
            return expr

        case FieldFilter():
            fields = field_map.get(condition.field, [condition.field])
            value = _format_value(condition.value)
            exprs = [f"{field} contains {value}" for field in fields]
            combined = " or ".join(exprs)
            if condition.op == "not_contains":
                return f"!({combined})"
            return f"({combined})" if len(exprs) > 1 else combined


def _build_filter_yql(
    filter_group: Filter,
    field_map: dict[str, list[str]],
    struct_map: dict[str, ArrayStructField],
) -> str:
    """Recursively build YQL for a filter group"""
    parts: list[str] = []
    # `contains` conditions grouped by struct to allow us to filter on more than 1 field of a struct.
    struct_operands: dict[str, list[str]] = {}

    for item in filter_group.filters:
        if isinstance(item, Filter):
            parts.append(_build_filter_yql(item, field_map, struct_map))
        elif isinstance(item, FieldFilter) and item.field in struct_map:
            struct = struct_map[item.field]
            operand = f"{struct.subfield} contains {_format_value(item.value)}"
            if item.op == "not_contains":
                parts.append(f"!({struct.array_field} contains sameElement({operand}))")
            else:
                struct_operands.setdefault(struct.array_field, []).append(operand)
        else:
            parts.append(_build_condition_yql(item, field_map))

    for array_field, operands in struct_operands.items():
        if filter_group.op == "and":
            # All conditions must match the same element.
            parts.append(f"{array_field} contains sameElement({', '.join(operands)})")
        else:
            # OR: each condition may match a different element.
            parts.extend(
                f"{array_field} contains sameElement({operand})" for operand in operands
            )

    if not parts:
        return ""

    joined = f" {filter_group.op} ".join(parts)

    # Wrap in parentheses if multiple parts
    return f"({joined})" if len(parts) > 1 else joined


def _build_filter_query(
    filter_group: Filter | None,
    field_map: dict[str, list[str]],
    struct_map: dict[str, ArrayStructField],
) -> str:
    """Build the WHERE clause from a filter group."""
    if filter_group is None:
        return ""
    yql = _build_filter_yql(filter_group, field_map, struct_map)
    return f" and {yql}" if yql else ""


def _facet_filter_label_type(condition: Condition) -> str | None:
    """Returns the label.type parsed label.id"""
    if (
        isinstance(condition, FieldFilter)
        and condition.field in ("labels.value.id", "concepts.value.id")
        and isinstance(condition.value, str)
    ):
        prefix, sep, _ = condition.value.partition("::")
        return prefix if sep else None
    if (
        isinstance(condition, FieldFilter)
        and condition.field == "labels.type"
        and isinstance(condition.value, str)
    ):
        return condition.value
    return None


def _prune_filter(
    filter_group: Filter | None,
    filter_method: Callable[[Condition], bool],
) -> Filter | None:
    """Return a copy of `filter_group` with a filter_method applied"""
    if filter_group is None:
        return None
    new_filters: list[Condition | Filter] = []
    for item in filter_group.filters:
        if isinstance(item, Filter):
            pruned = _prune_filter(item, filter_method)
            if pruned is not None:
                new_filters.append(pruned)
        elif not filter_method(item):
            new_filters.append(item)
    if not new_filters:
        return None
    return Filter(op=filter_group.op, filters=new_filters)


def _get_label_types_from_filters(filter_group: Filter | None) -> set[str]:
    """Returns a set of `labels.types` recursively from the `filter_group`"""
    if filter_group is None:
        return set()

    label_types: set[str] = set()
    for filter_item in filter_group.filters:
        # If this is a `Filter`, recurse
        if isinstance(filter_item, Filter):
            label_types |= _get_label_types_from_filters(filter_item)
        # Otherwise get the `label_type` from the condition
        else:
            label_type = _facet_filter_label_type(filter_item)
            if label_type is not None:
                label_types.add(label_type)

    return label_types


# endregion Filters

# region Document sort (Vespa ranking.sorting)


def _document_sort_ranking_string(vespa_attr: str, direction: str) -> str:
    """
    Build Vespa ``ranking.sorting`` for a document sort attribute.

    Always pushes ``missing`` values to the end of the list.
    https://docs.vespa.ai/en/reference/querying/sorting-language.html#missing

    :param vespa_attr: First mapped field name from
        :data:`sort_field_to_vespa_field_map`
    :type vespa_attr: str
    :param direction: ``asc`` or ``desc``
    :type direction: str
    :return: Vespa sorting expression fragment
    :rtype: str
    :raises AssertionError: if ``vespa_attr`` is not handled
    """
    sign = "+" if direction == "asc" else "-"
    if vespa_attr == "attributes_published_date":
        return f"{sign}missing(attributes_published_date,last)"
    if vespa_attr == "title_sort":
        return f"{sign}missing(title_sort,last)"
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


# region Documents
documents_filter_field_to_vespa_field_map = {
    "labels.value.id": ["labels.id", "concepts.id"],
    "labels.value.value": ["labels.value", "concepts.value"],
    "labels.type": ["labels.relationship"],
}
documents_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {}


class DevVespaInstanceAddIn:
    """Surfaces the personal dev instance name (from settings) onto the engine id/config."""

    settings: "Settings"

    @property
    def instance_name(self) -> str | None:
        """Name of the specific instance of the search engine"""
        return self.settings.vespa_dev_instance_name


class DevVespaDocumentSearchEngine(DevVespaInstanceAddIn, SearchEngine[Document]):
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
            where += _build_filter_query(
                filters,
                field_map=documents_filter_field_to_vespa_field_map,
                struct_map=documents_filter_struct_field_to_vespa_field_map,
            )

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
                        idx=passage.get("idx", 0),
                        text=bolded_text,
                        language=passage.get("language", ""),
                        type=passage.get("type", ""),
                        type_confidence=passage.get("type_confidence", 0.0),
                        page_number=passage.get("page_number", 0),
                        pages=passage.get("pages", []),
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

    def get(self, document_id: str) -> Document | None:
        """Fetch a single document by id, parsed from its stored document_source."""
        endpoint = f"{self.settings.vespa_endpoint}/document/v1/documents/documents/docid/{document_id}"
        logger.info("Vespa request started [documents.get]")
        try:
            response = requests.get(
                endpoint,
                timeout=API_TIMEOUT,
                headers={"Authorization": f"Bearer {self.settings.vespa_read_token}"},
            )
        except Exception as exc:
            raise VespaError("Vespa request failed") from exc
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        if response.status_code != HTTPStatus.OK:
            body_preview = (response.text or "")[:HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS]
            raise VespaError(
                f"Vespa returned status {response.status_code}: {body_preview}"
            )

        document_source = response.json().get("fields", {}).get("document_source")
        if not document_source:
            return None

        return Document.model_validate_json(document_source)

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
            where += _build_filter_query(
                filters,
                field_map=documents_filter_field_to_vespa_field_map,
                struct_map=documents_filter_struct_field_to_vespa_field_map,
            )

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

    def _run_facet_query(
        self,
        query: str | None,
        where_filter: Filter | None,
        group_attributes: list[str],
    ) -> dict[str, dict[tuple[str, str], tuple[Label, int]]]:
        """Run a Vespa grouping query and return label/concept buckets partitioned by attribute."""
        where = "true"
        if query:
            where += self._userQuery
        where += _build_filter_query(
            where_filter,
            field_map=documents_filter_field_to_vespa_field_map,
            struct_map=documents_filter_struct_field_to_vespa_field_map,
        )

        inner_groups = [
            G.all(
                G.group(attr),
                # TODO: Pagination on groups if we hit this limit
                G.max(5000),
                G.order(-G.count()),
                G.each(G.output(G.count())),
            )
            for attr in group_attributes
        ]
        grouping = G.all(*inner_groups)
        yql = f"select {', '.join(group_attributes)} from documents where {where} | {grouping}"

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
            request_context="documents.facets",
        )
        if response is None:
            return {}

        root_children: list[dict] = response.get("root", {}).get("children") or []
        groups: list[dict] = (
            root_children[0].get("children", []) if root_children else []
        )
        group_values: list[dict] = []
        for group in groups:
            group_values.extend(group.get("children", []))

        by_type: dict[str, dict[tuple[str, str], tuple[Label, int]]] = {}
        for gv in group_values:
            label_type, label_id, label_value = self.parse_label_type_id_value(
                gv.get("value", "")
            )
            label_type = label_type or MISSING_PLACEHOLDER
            count = gv.get("fields", {}).get("count()", 0)
            label = Label(id=label_id, value=label_value, type=label_type)
            by_type.setdefault(label_type, {})[(label_id, label_value)] = (
                label,
                count,
            )
        return by_type

    def labels_value_type_facets(
        self,
        query: str | None,
        filters_json_string: str | None = None,
    ) -> dict[str, list[CountAggregation[Label]]]:
        """
        Compute disjunctive facet counts partitioned by `label.type`. AKA faceted search.

        The query generally coming across is
        - grouped by `label.type`
        - each filter within that is joined by `OR`
        - each group is joined by `AND`

        Example:
        - (category::1 OR category::2) OR (geography::USA OR geography::GBR)
        """
        filters = (
            Filter.model_validate_json(filters_json_string)
            if filters_json_string
            else None
        )

        facet_label_types = _get_label_types_from_filters(filters)
        facet_requests: dict[str, Filter | None] = {"filtered_labels": filters}
        for label_type in facet_label_types:
            facet_requests[f"filter_{label_type}"] = _prune_filter(
                filters,
                lambda c, t=label_type: _facet_filter_label_type(c) == t,
            )

        responses: dict[str, dict[str, dict[tuple[str, str], tuple[Label, int]]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(facet_requests))) as pool:
            futures = {
                pool.submit(
                    self._run_facet_query,
                    query,
                    plan,
                    [
                        "labels_type_id_value_attribute",
                        "concepts_type_id_value_attribute",
                    ],
                ): name
                for name, plan in facet_requests.items()
            }
            for future in as_completed(futures):
                responses[futures[future]] = future.result()

        result: dict[str, list[CountAggregation[Label]]] = {}
        for label_type, labels_for_type in responses["filtered_labels"].items():
            if label_type in facet_label_types:
                counts_for_type = responses[f"filter_{label_type}"].get(label_type, {})
            else:
                counts_for_type = labels_for_type

            entries: list[CountAggregation[Label]] = [
                CountAggregation(count=count, value=label)
                for label, count in counts_for_type.values()
            ]
            entries.sort(key=lambda c: -c.count)
            result[label_type] = entries

        return result

    def labels_type_facets(
        self,
        query: str | None,
        filters_json_string: str | None = None,
    ) -> dict[str, list[CountAggregation[Label]]]:
        """Compute disjunctive facet counts partitioned by `label.relationship`."""
        filters = (
            Filter.model_validate_json(filters_json_string)
            if filters_json_string
            else None
        )

        facet_label_types = _get_label_types_from_filters(filters)
        facet_requests: dict[str, Filter | None] = {"filtered_labels": filters}
        for label_type in facet_label_types:
            facet_requests[f"filter_{label_type}"] = _prune_filter(
                filters,
                lambda c, t=label_type: _facet_filter_label_type(c) == t,
            )

        responses: dict[str, dict[str, dict[tuple[str, str], tuple[Label, int]]]] = {}
        with ThreadPoolExecutor(max_workers=max(1, len(facet_requests))) as pool:
            futures = {
                pool.submit(
                    self._run_facet_query,
                    query,
                    plan,
                    ["labels_relationship_id_value_attribute"],
                ): name
                for name, plan in facet_requests.items()
            }
            for future in as_completed(futures):
                responses[futures[future]] = future.result()

        result: dict[str, list[CountAggregation[Label]]] = {}
        for label_type, labels_for_type in responses["filtered_labels"].items():
            if label_type in facet_label_types:
                counts_for_type = responses[f"filter_{label_type}"].get(label_type, {})
            else:
                counts_for_type = labels_for_type

            entries: list[CountAggregation[Label]] = [
                CountAggregation(count=count, value=label)
                for label, count in counts_for_type.values()
            ]
            entries.sort(key=lambda c: -c.count)
            result[label_type] = entries

        return result

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()


class DevVespaPrincipalDocumentSearchEngine(DevVespaDocumentSearchEngine):
    """
    Search engine for principal documents.

    Overrides calls to .search with a filter for principal documents, so the engine
    can be used against relevance tests.
    """

    def search(
        self,
        query: str | None,
        pagination: Pagination,
        order_by: list[OrderBy],
        filters_json_string: str | None = None,
    ) -> ListResponse[Document]:
        """Search principal documents"""

        principal_filter = Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id",
                    op="contains",
                    value="status::Principal",
                )
            ],
        )

        if filters_json_string is not None:
            caller_filter = Filter.model_validate_json(filters_json_string)
            merged_filter = Filter(op="and", filters=[principal_filter, caller_filter])
        else:
            merged_filter = principal_filter

        return super().search(
            query, pagination, order_by, merged_filter.model_dump_json()
        )


passages_filter_field_to_vespa_field_map: dict[str, list[str]] = {
    "document_id": ["document_id"],
    "principal_id": ["principal_id"],
}
passages_filter_struct_field_to_vespa_field_map: dict[str, ArrayStructField] = {}


class DevVespaPassageSearchEngine(DevVespaInstanceAddIn, SearchEngine[Passage]):
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
        filters_json_string: str | None = None,
    ) -> ListResponse[Passage]:
        """Fetch a list of relevant passage search results."""
        where = "true"

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

        request_body: dict[str, Any] = {
            "yql": yql,
            "query": query,
            "hits": pagination.page_size,
            "offset": (pagination.page_token - 1) * pagination.page_size,
            "timeout": "5s",
            "model.language": "en",
            # TODO: always requesting debug-summary here (rather than only
            # when self.debug) so `Passage.tokens` (text_tokens) is populated
            # on every live request, not just debug/CLI usage. This uses
            # `from-disk` field access instead of in-memory attributes, so it
            # is slower per-query than the default summary - accepted as a
            # simplicity-over-performance tradeoff for now. Push back to only
            # when self.debug once once `tokens`' field shape/necessity is settled
            # `tokens`' field shape/necessity is settled (see Passage.tokens).
            "presentation.summary": "debug-summary",
        }
        if self.debug:
            request_body["ranking.profile"] = "nativerank"

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
                    idx=fields.get("idx", 0),
                    text=fields.get("text", ""),
                    language=fields.get("language", ""),
                    type=fields.get("type", ""),
                    type_confidence=fields.get("type_confidence", 0.0),
                    page_number=fields.get("page_number", 0),
                    pages=fields.get("pages", []),
                    pages_with_bounding_boxes=fields.get("page_bounding_boxes", []),
                    heading_id=fields.get("heading_id"),
                    heading_text=fields.get("heading_text"),
                    document_id=fields.get("document_id", ""),
                    principal_id=fields.get("principal_id"),
                    tokens=fields.get("text_tokens") or [],
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
        if response is None:
            return ListResponse(results=[], total_size=None, next_page_token=None)
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
