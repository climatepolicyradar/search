"""Unit tests for Vespa sort/ranking-override translation."""

from search.engines import OrderBy
from search.engines.vespa_query.sorting import _ranking_overrides_for_passage_order_by


def test_passage_order_by_idx_asc_sorts_missing_last() -> None:
    """Ascending idx sort pushes missing values to the end."""
    overrides = _ranking_overrides_for_passage_order_by(
        [OrderBy(field="idx", direction="asc")]
    )
    assert overrides == {
        "ranking.profile": "unranked",
        "ranking.sorting": "+missing(idx,last)",
        "sorting.degrading": False,
    }


def test_passage_order_by_idx_desc_sorts_missing_last() -> None:
    """Descending idx sort also pushes missing values to the end."""
    overrides = _ranking_overrides_for_passage_order_by(
        [OrderBy(field="idx", direction="desc")]
    )
    assert overrides["ranking.sorting"] == "-missing(idx,last)"


def test_passage_order_by_relevance_is_a_no_op() -> None:
    """Relevance sort applies no ranking overrides (default rank-profile order)."""
    overrides = _ranking_overrides_for_passage_order_by(
        [OrderBy(field="relevance", direction="desc")]
    )
    assert overrides == {}


def test_passage_order_by_empty_list_is_a_no_op() -> None:
    """No order_by clauses means no ranking overrides."""
    assert _ranking_overrides_for_passage_order_by([]) == {}
