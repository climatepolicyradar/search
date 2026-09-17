"""Translate ``order_by`` clauses into Vespa ``ranking.sorting`` request fields."""

from __future__ import annotations

from typing import Any

from search.engines import OrderBy
from search.log import get_logger

logger = get_logger(__name__)

# region Document sort (Vespa ranking.sorting)

sort_field_to_vespa_field_map = {
    "attributes.published_date": ["attributes_published_date"],
    "title": ["title_sort"],
}

# Public API field names for ``order_by`` (JSON paths + ``relevance``), aligned
# with :data:`sort_field_to_vespa_field_map` keys.
DOCUMENT_SORT_API_FIELDS: frozenset[str] = frozenset(
    {"relevance", *sort_field_to_vespa_field_map.keys()}
)

# Public API field names for ``order_by`` on ``/passages``.
PASSAGE_SORT_API_FIELDS: frozenset[str] = frozenset({"relevance", "idx"})


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
    ``relevance`` keeps the engine's configured rank profile (no ``ranking.sorting``).

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

# region Passage sort (Vespa ranking.sorting)

passage_sort_field_to_vespa_field_map: dict[str, list[str]] = {
    "idx": ["idx"],
}


def _passage_sort_ranking_string(vespa_attr: str, direction: str) -> str:
    """
    Build Vespa ``ranking.sorting`` for a passage sort attribute.

    Always pushes ``missing`` values to the end of the list.
    https://docs.vespa.ai/en/reference/querying/sorting-language.html#missing

    :param vespa_attr: First mapped field name from
        :data:`passage_sort_field_to_vespa_field_map`
    :type vespa_attr: str
    :param direction: ``asc`` or ``desc``
    :type direction: str
    :return: Vespa sorting expression fragment
    :rtype: str
    :raises AssertionError: if ``vespa_attr`` is not handled
    """
    sign = "+" if direction == "asc" else "-"
    if vespa_attr == "idx":
        return f"{sign}missing(idx,last)"
    raise AssertionError(f"unexpected Vespa sort attribute {vespa_attr!r}")


def _ranking_overrides_for_passage_order_by(
    order_by: list[OrderBy],
) -> dict[str, Any]:
    """
    Translate ``order_by`` clauses into Vespa ranking request fields.

    Only the first clause is applied (multilevel sorts can be added later).
    ``relevance`` keeps the engine's configured rank profile (no ``ranking.sorting``).

    :param order_by: Parsed ``<field> <direction>`` clauses (``idx``
        plus ``relevance``)
    :type order_by: list[OrderBy]
    :return: Key/value fragments to merge into the Vespa JSON body
    :rtype: dict[str, Any]
    :raises ValueError: if the field is not supported for passages
    """
    if not order_by:
        return {}
    primary = order_by[0]
    if primary.field not in PASSAGE_SORT_API_FIELDS:
        raise ValueError(
            f"order_by field {primary.field!r} is not supported for passages; "
            f"expected one of: {sorted(PASSAGE_SORT_API_FIELDS)}"
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

    # ``PASSAGE_SORT_API_FIELDS`` is ``relevance`` plus map keys, so this
    # lookup is always valid here.
    vespa_attr = passage_sort_field_to_vespa_field_map[primary.field][0]
    sorting = _passage_sort_ranking_string(vespa_attr, primary.direction)
    return {
        "ranking.profile": "unranked",
        "ranking.sorting": sorting,
        "sorting.degrading": False,
    }


# endregion Passage sort
