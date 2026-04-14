from typing import Annotated

from fastapi import HTTPException, Query

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import DOCUMENT_SEARCH_ORDER_FIELDS

DOCUMENTS_ORDER_BY_DESCRIPTION = (
    "Comma-separated sort clauses: `<field> <direction>` (AIP-132). "
    "Supported fields: `relevance`, `published_timestamp` "
    "(from document `published_date`), `title_sort` (lowercased title). "
    "Directions: `asc`, `desc`. "
    "Examples: `relevance desc`, `published_timestamp desc` (most recent), "
    "`published_timestamp asc` (oldest; undated documents last), "
    "`title_sort asc` (A–Z), `title_sort desc` (Z–A)."
)


def pagination(page_token: int = 1, page_size: int = 10):
    """
    Shared pagination parameters

    @see: https://fastapi.tiangolo.com/tutorial/dependencies/#import-depends
    @see: https://google.aip.dev/158
    """
    return Pagination(page_token=page_token, page_size=page_size)


def _parse_order_by_string(raw: str) -> list[OrderBy]:
    """
    Parse a Google AIP-132 ``order_by`` query string.

    :param raw: Raw query value, comma-separated clauses
    :type raw: str
    :return: Structured order clauses
    :rtype: list[OrderBy]
    :raises HTTPException: if the string is empty or malformed
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
            raise HTTPException(
                status_code=400,
                detail="order_by contains an empty field name",
            )
        if direction not in ("asc", "desc"):
            raise HTTPException(
                status_code=400,
                detail=(f"invalid sort direction {direction!r}; use asc or desc"),
            )
        result.append(OrderBy(field=field, direction=direction))
    if not result:
        raise HTTPException(
            status_code=400,
            detail="order_by must contain at least one non-empty clause",
        )
    return result


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
    return _parse_order_by_string(order_by_raw)


def documents_order_by(
    order_by_raw: Annotated[
        str,
        Query(
            alias="order_by",
            description=DOCUMENTS_ORDER_BY_DESCRIPTION,
            example="published_timestamp desc",
        ),
    ] = "relevance desc",
) -> list[OrderBy]:
    """Parse ``order_by`` and restrict fields to those supported on ``/documents``."""
    parsed = _parse_order_by_string(order_by_raw)
    for clause in parsed:
        if clause.field not in DOCUMENT_SEARCH_ORDER_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"order_by field {clause.field!r} is not supported for "
                    f"/documents; allowed: {sorted(DOCUMENT_SEARCH_ORDER_FIELDS)}"
                ),
            )
    return parsed
