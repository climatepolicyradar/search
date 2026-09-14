import json
from datetime import datetime
from typing import Annotated, get_args

from fastapi import HTTPException, Query, status
from pydantic import BaseModel

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DOCUMENT_SORT_API_FIELDS,
    PASSAGE_SORT_API_FIELDS,
    ArrayStructField,
    AttributesCondition,
    FieldFilter,
    Filter,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)

DOCUMENTS_ORDER_BY_DESCRIPTION = (
    "Comma-separated sort clauses: `<field> <direction>` (AIP-132). "
    "Supported fields: `relevance`, `attributes.published_date` "
    "(from document `published_date`), `title` (document title; lowercased for "
    "sort). "
    "Directions: `asc`, `desc`. "
    "Examples: `relevance desc`, `attributes.published_date desc` (most recent), "
    "`attributes.published_date asc` (oldest; undated documents last), "
    "`title asc` (A-Z), `title desc` (Z-A)."
)

PASSAGES_ORDER_BY_DESCRIPTION = (
    "Comma-separated sort clauses: `<field> <direction>` (AIP-132). "
    "Supported fields: `relevance`, `idx`. "
    "Directions: `asc`, `desc`. "
    "Defaults to `idx asc` when omitted. "
    "Examples: `idx asc` (default; reading order), `relevance desc` "
    "(best matches first)."
)


def _literal_options(model: type[BaseModel], field_name: str) -> str:
    """
    Render a model field's ``Literal`` options as a JSON alternation.

    Read off the model rather than retyped, so the published grammar tracks
    the types. Parsing ``filters`` as a model instead of a raw JSON string
    would put all of this in the generated component schema and make this
    function deletable.

    :param model: Model owning the field
    :type model: type[BaseModel]
    :param field_name: Field whose annotation is a ``Literal``
    :type field_name: str
    :return: Options joined with ``|``, each JSON-quoted
    :rtype: str
    """
    options = get_args(model.model_fields[field_name].annotation)
    return "|".join(json.dumps(option) for option in options)


FILTERS_GRAMMAR_DESCRIPTION = (
    "URL-encoded JSON filter tree, ANDed with `query`. Groups nest freely. "
    f'Group: {{"op": {_literal_options(Filter, "op")}, '
    '"filters": [<group>|<condition>]}. '
    f'Field condition: {{"field": <name>, "op": {_literal_options(FieldFilter, "op")}, '
    '"value": <string|number|boolean>}. '
    f'Attribute condition: {{"field": {_literal_options(AttributesCondition, "field")}, '
    f'"key": <string>, "op": {_literal_options(AttributesCondition, "op")}, '
    '"value": <string|number|boolean>}. '
)


def _filters_description(
    field_map: dict[str, list[str]],
    struct_map: dict[str, ArrayStructField],
) -> str:
    """Build a `filters` description for one endpoint's filterable fields."""
    aliased = ", ".join(f"`{name}`" for name in sorted({*field_map, *struct_map}))
    return (
        f"{FILTERS_GRAMMAR_DESCRIPTION}"
        f"Recognised field names: {aliased}. Any other name is passed to the "
        "index unchanged. Semantics and worked examples: /search/llms.txt"
    )


DOCUMENTS_FILTERS_DESCRIPTION = _filters_description(
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)
PASSAGES_FILTERS_DESCRIPTION = _filters_description(
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)
LABELS_FILTERS_DESCRIPTION = _filters_description(
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
)


def pagination(page_token: int = 1, page_size: int = 10):
    """
    Shared pagination parameters

    @see: https://fastapi.tiangolo.com/tutorial/dependencies/#import-depends
    @see: https://google.aip.dev/158
    """
    return Pagination(page_token=page_token, page_size=page_size)


def parse_order_by_clauses(raw: str) -> list[OrderBy]:
    """
    Parse a Google AIP-132 ``order_by`` query string.

    :param raw: Raw query value, comma-separated clauses
    :type raw: str
    :return: Structured order clauses
    :rtype: list[OrderBy]
    :raises ValueError: if the string is empty or malformed
    """
    result: list[OrderBy] = []
    for segment in raw.split(","):
        segment = segment.strip()
        if not segment:
            continue
        parts = segment.rsplit(" ", 1)
        if len(parts) == 1:
            field, direction = parts[0], "desc"
        else:
            field, direction = parts[0].strip(), parts[1].strip().lower()
        if not field:
            raise ValueError("order_by contains an empty field name")
        if direction not in ("asc", "desc"):
            raise ValueError(
                f"invalid sort direction {direction!r}; use asc or desc",
            )
        result.append(OrderBy(field=field, direction=direction))
    if not result:
        raise ValueError("order_by must contain at least one non-empty clause")
    return result


def _parse_order_by_http(raw: str) -> list[OrderBy]:
    """
    Parse ``order_by`` and map parse errors to HTTP 400.

    :param raw: Raw query string from the client
    :type raw: str
    :return: Parsed clauses
    :rtype: list[OrderBy]
    :raises HTTPException: with status 400 when the string is invalid
    """
    try:
        return parse_order_by_clauses(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


def order_by(
    order_by_raw: Annotated[
        str,
        Query(
            alias="order_by",
            description=(
                "Comma-separated `<field> <direction>` sort clauses (AIP-132). "
                "Directions: asc, desc."
            ),
        ),
    ] = "relevance desc",
) -> list[OrderBy]:
    """
    Shared order-by dependency for list endpoints.

    @see: https://fastapi.tiangolo.com/tutorial/dependencies/#import-depends
    @see: https://google.aip.dev/132#ordering
    """
    return _parse_order_by_http(order_by_raw)


def documents_order_by(
    order_by_raw: Annotated[
        str,
        Query(
            alias="order_by",
            description=DOCUMENTS_ORDER_BY_DESCRIPTION,
            examples=["attributes.published_date desc"],
        ),
    ] = "relevance desc",
) -> list[OrderBy]:
    """
    Parse ``order_by`` and restrict fields to those supported on ``/documents``.

    :param order_by_raw: Raw ``order_by`` query string
    :type order_by_raw: str
    :return: Parsed clauses whose fields are public JSON paths
    :rtype: list[OrderBy]
    :raises HTTPException: if parsing fails or a field is not supported
    """
    clauses = _parse_order_by_http(order_by_raw)
    for clause in clauses:
        if clause.field not in DOCUMENT_SORT_API_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"order_by field {clause.field!r} is not supported for "
                    f"/documents; allowed: {sorted(DOCUMENT_SORT_API_FIELDS)}"
                ),
            )
    return clauses


def passages_order_by(
    order_by_raw: Annotated[
        str,
        Query(
            alias="order_by",
            description=PASSAGES_ORDER_BY_DESCRIPTION,
            examples=["idx asc"],
        ),
    ] = "idx asc",
) -> list[OrderBy]:
    """
    Parse ``order_by`` and restrict fields to those supported on ``/passages``.

    :param order_by_raw: Raw ``order_by`` query string
    :type order_by_raw: str
    :return: Parsed clauses whose fields are public JSON paths
    :rtype: list[OrderBy]
    :raises HTTPException: if parsing fails or a field is not supported
    """
    clauses = _parse_order_by_http(order_by_raw)
    for clause in clauses:
        if clause.field not in PASSAGE_SORT_API_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"order_by field {clause.field!r} is not supported for "
                    f"/passages; allowed: {sorted(PASSAGE_SORT_API_FIELDS)}"
                ),
            )
    return clauses


def _normalise_datetime_value(value: str) -> int:
    """Convert an ISO-8601 datetime string to epoch seconds."""
    normalised = value.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalised).timestamp())


def _normalise_filter_group(filter_group: Filter) -> None:
    """Normalise supported filter values in-place."""
    for item in filter_group.filters:
        if isinstance(item, Filter):
            _normalise_filter_group(item)
            continue
        if (
            isinstance(item, AttributesCondition)
            and item.field == "attributes.published_date"
            and isinstance(item.value, str)
        ):
            try:
                item.value = _normalise_datetime_value(item.value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "published_date filters must use ISO 8601 datetimes, "
                        f"received {item.value!r}"
                    ),
                ) from exc


def normalise_filters(filters_json_string: str | None) -> str | None:
    """
    Parse and normalise filter JSON before it reaches the search engine.

    ``attributes.published_date`` values are converted from ISO-8601 datetime
    strings to epoch seconds at the API boundary.
    """
    if filters_json_string is None:
        return None
    try:
        filters = Filter.model_validate_json(filters_json_string)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    _normalise_filter_group(filters)
    return filters.model_dump_json()
