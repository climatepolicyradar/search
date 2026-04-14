from typing import Annotated, Any

from fastapi import HTTPException, Query
from pydantic import BeforeValidator, TypeAdapter, ValidationError

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import DOCUMENT_SORT_API_FIELDS

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


def _coerce_order_by_query(value: Any) -> list[OrderBy]:
    """
    Pydantic ``BeforeValidator`` hook: accept only string input for order_by.

    :param value: Raw dependency value (must be ``str``)
    :type value: Any
    :return: Parsed clauses
    :rtype: list[OrderBy]
    :raises TypeError: if ``value`` is not a string
    :raises ValueError: delegated from :func:`parse_order_by_clauses`
    """
    if not isinstance(value, str):
        raise TypeError("order_by must be a string")
    return parse_order_by_clauses(value)


OrderByQueryList = Annotated[list[OrderBy], BeforeValidator(_coerce_order_by_query)]

ORDER_BY_QUERY_ADAPTER = TypeAdapter(OrderByQueryList)


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
    try:
        return ORDER_BY_QUERY_ADAPTER.validate_python(order_by_raw)
    except (ValueError, TypeError, ValidationError) as exc:
        detail = str(exc)
        if isinstance(exc, ValidationError):
            err0 = exc.errors()[0]
            detail = err0.get("msg", detail)
        raise HTTPException(status_code=400, detail=detail) from exc


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
    try:
        parsed = ORDER_BY_QUERY_ADAPTER.validate_python(order_by_raw)
    except (ValueError, TypeError, ValidationError) as exc:
        detail = str(exc)
        if isinstance(exc, ValidationError):
            err0 = exc.errors()[0]
            detail = err0.get("msg", detail)
        raise HTTPException(status_code=400, detail=detail) from exc
    for clause in parsed:
        if clause.field not in DOCUMENT_SORT_API_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"order_by field {clause.field!r} is not supported for "
                    f"/documents; allowed: {sorted(DOCUMENT_SORT_API_FIELDS)}"
                ),
            )
    return parsed
