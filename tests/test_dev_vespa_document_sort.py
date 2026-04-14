"""Unit tests for document ``order_by`` → Vespa ranking request mapping."""

import pytest

from search.engines import OrderBy
from search.engines.dev_vespa import _ranking_overrides_for_document_order_by


@pytest.mark.parametrize(
    ("clauses", "expected_subset"),
    [
        (
            [OrderBy(field="relevance", direction="desc")],
            {},
        ),
        (
            [OrderBy(field="published_timestamp", direction="desc")],
            {
                "ranking.profile": "unranked",
                "ranking.sorting": "-published_timestamp",
                "sorting.degrading": False,
            },
        ),
        (
            [OrderBy(field="published_timestamp", direction="asc")],
            {
                "ranking.profile": "unranked",
                "ranking.sorting": (
                    "+missing(published_timestamp,last) +published_timestamp"
                ),
                "sorting.degrading": False,
            },
        ),
        (
            [OrderBy(field="title_sort", direction="asc")],
            {
                "ranking.profile": "unranked",
                "ranking.sorting": "+title_sort",
                "sorting.degrading": False,
            },
        ),
        (
            [OrderBy(field="title_sort", direction="desc")],
            {
                "ranking.profile": "unranked",
                "ranking.sorting": "-title_sort",
                "sorting.degrading": False,
            },
        ),
    ],
)
def test_ranking_overrides_for_document_order_by(
    clauses: list[OrderBy],
    expected_subset: dict[str, str | bool],
) -> None:
    """
    Check non-relevance sorts set ``unranked``, ``ranking.sorting``, and degrading off.

    :param clauses: Parsed API order clauses
    :type clauses: list[OrderBy]
    :param expected_subset: Expected key/value subset of the Vespa request fragment
    :type expected_subset: dict[str, str | bool]
    """
    got = _ranking_overrides_for_document_order_by(clauses)
    for key, val in expected_subset.items():
        assert got.get(key) == val, f"{key!r}: expected {val!r}, got {got.get(key)!r}"


def test_ranking_overrides_rejects_unknown_field() -> None:
    """:raises ValueError: when the document sort field is not allow-listed"""
    with pytest.raises(ValueError, match="not supported"):
        _ranking_overrides_for_document_order_by(
            [OrderBy(field="nope", direction="asc")]
        )
