import json

import pytest
from pydantic import HttpUrl

from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    Filter,
    Settings,
    _document_sort_ranking_string,
)
from search.label import Label


@pytest.mark.parametrize(
    "s, expected",
    [
        (
            "geography::geography::USA::United States of America",
            ("geography", "geography::USA", "United States of America"),
        ),
        (
            "geography::geography::USA_west::United States of America",
            ("geography", "geography::USA_west", "United States of America"),
        ),
    ],
)
def test_parse_label_type_id_value(s, expected):
    assert DevVespaDocumentSearchEngine.parse_label_type_id_value(s) == expected


@pytest.mark.parametrize(
    ("field", "direction", "expected"),
    [
        (
            "attributes_published_date",
            "asc",
            "+missing(attributes_published_date,last)",
        ),
        (
            "attributes_published_date",
            "desc",
            "-missing(attributes_published_date,last)",
        ),
        ("title_sort", "asc", "+missing(title_sort,last)"),
        ("title_sort", "desc", "-missing(title_sort,last)"),
    ],
)
def test_document_sort_ranking_string_puts_missing_values_last(
    field: str, direction: str, expected: str
) -> None:
    assert _document_sort_ranking_string(field, direction) == expected


def _make_engine() -> DevVespaDocumentSearchEngine:
    settings = Settings(
        vespa_endpoint=HttpUrl("https://example.invalid"),  # pyright: ignore[reportArgumentType]
        vespa_read_token="test-token",  # nosec B106
    )
    return DevVespaDocumentSearchEngine(settings=settings)


def _label_bucket(
    label_type: str, label_id: str, label_value: str, count: int
) -> tuple[tuple[str, str], tuple[Label, int]]:
    return (
        (label_id, label_value),
        (Label(id=label_id, value=label_value, type=label_type), count),
    )


def test_facets_with_no_filters_emits_universe_counts(monkeypatch) -> None:
    """With no filters, only the universe query runs and its counts are returned."""
    engine = _make_engine()

    universe = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 10),
            _label_bucket("category", "category::Policy", "Policy", 7),
        ]),
        "geography": dict([
            _label_bucket("geography", "geography::USA", "USA", 5),
        ]),
    }
    calls: list[Filter | None] = []

    def fake_run(_query, where_filter):
        calls.append(where_filter)
        return universe

    monkeypatch.setattr(engine, "_run_facet_query", fake_run)

    result = engine.facets(query=None, filters_json_string=None)

    # Only the universe query runs.
    assert calls == [None]
    assert set(result.keys()) == {"category", "geography"}
    assert [(c.value.id, c.count) for c in result["category"]] == [
        ("category::Law", 10),
        ("category::Policy", 7),
    ]
    assert [(c.value.id, c.count) for c in result["geography"]] == [
        ("geography::USA", 5),
    ]


def test_facets_disjunctive_keeps_unselected_within_group_alive(
    monkeypatch,
) -> None:
    """Must not narrow counts in the disjunctive group"""
    engine = _make_engine()

    # Universe (all facet filters peeled): every label reachable under the
    # user's query and non-facet filters.
    universe = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 10),
            _label_bucket("category", "category::Policy", "Policy", 7),
            _label_bucket("category", "category::MCF", "MCF", 3),
        ]),
        "geography": dict([
            _label_bucket("geography", "geography::USA", "USA", 6),
            _label_bucket("geography", "geography::AUS", "AUS", 4),
            _label_bucket("geography", "geography::GBR", "GBR", 2),
        ]),
    }

    # Natural query: full user filters (category=Law). Category collapses to
    # Law; geography is restricted to docs tagged Law, so GBR is absent.
    natural = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 10),
        ]),
        "geography": dict([
            _label_bucket("geography", "geography::USA", "USA", 6),
            _label_bucket("geography", "geography::AUS", "AUS", 4),
        ]),
    }

    def fake_run(_query, where_filter):
        if where_filter is None:
            return universe
        # category=Law present → natural; category peeled (no filters left) → universe.
        return natural if "category::Law" in str(where_filter) else universe

    monkeypatch.setattr(engine, "_run_facet_query", fake_run)

    filters_json = json.dumps(
        {
            "op": "and",
            "filters": [
                {
                    "field": "labels.value.id",
                    "op": "contains",
                    "value": "category::Law",
                },
            ],
        }
    )

    result = engine.facets(query=None, filters_json_string=filters_json)

    # category is active → use the category-peeled plan: all three alive.
    category_counts = {c.value.id: c.count for c in result["category"]}
    assert category_counts == {
        "category::Law": 10,
        "category::Policy": 7,
        "category::MCF": 3,
    }

    # geography is not active → use the natural plan. GBR is in the universe
    # but absent from natural → reported as 0 so the UI can gray it out.
    geography_counts = {c.value.id: c.count for c in result["geography"]}
    assert geography_counts == {
        "geography::USA": 6,
        "geography::AUS": 4,
        "geography::GBR": 0,
    }


def test_facets_not_contains_lets_excluded_value_show_real_count(
    monkeypatch,
) -> None:
    """`not_contains` should not affect counts of the disjunctive group"""
    engine = _make_engine()

    universe = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 12),
            _label_bucket("category", "category::Policy", "Policy", 8),
        ]),
        "status": dict([
            _label_bucket("status", "status::Principal", "Principal", 10),
            _label_bucket("status", "status::Merged", "Merged", 5),
        ]),
    }
    # Natural: (category=Law AND NOT status=Merged) → Merged absent.
    natural = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 9),
        ]),
        "status": dict([
            _label_bucket("status", "status::Principal", "Principal", 9),
        ]),
    }
    # status-peeled: just (category=Law) → Merged reappears with real count.
    status_peeled = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 12),
        ]),
        "status": dict([
            _label_bucket("status", "status::Principal", "Principal", 9),
            _label_bucket("status", "status::Merged", "Merged", 3),
        ]),
    }
    # category-peeled: just (NOT status=Merged) → Policy stays alive.
    category_peeled = {
        "category": dict([
            _label_bucket("category", "category::Law", "Law", 9),
            _label_bucket("category", "category::Policy", "Policy", 6),
        ]),
        "status": dict([
            _label_bucket("status", "status::Principal", "Principal", 10),
        ]),
    }

    def fake_run(_query, where_filter):
        if where_filter is None:
            return universe
        flat = where_filter.model_dump_json()
        has_category = "category::Law" in flat
        has_status = "status::Merged" in flat
        if has_category and has_status:
            return natural
        if has_category and not has_status:
            return status_peeled
        if not has_category and has_status:
            return category_peeled
        raise AssertionError(f"unexpected plan: {where_filter}")

    monkeypatch.setattr(engine, "_run_facet_query", fake_run)

    filters_json = json.dumps(
        {
            "op": "and",
            "filters": [
                {
                    "field": "labels.value.id",
                    "op": "contains",
                    "value": "category::Law",
                },
                {
                    "field": "labels.value.id",
                    "op": "not_contains",
                    "value": "status::Merged",
                },
            ],
        }
    )

    result = engine.facets(query=None, filters_json_string=filters_json)

    # `status` is active even though selection is `not_contains`. The peeled
    # plan drops the negation, so Merged is back with its honest count.
    status_counts = {c.value.id: c.count for c in result["status"]}
    assert status_counts == {
        "status::Principal": 9,
        "status::Merged": 3,
    }

    # `category` is active → category-peeled plan supplies counts. Policy
    # survives even though the natural query (with status exclusion) would
    # have hidden any docs that don't match (NOT Merged).
    category_counts = {c.value.id: c.count for c in result["category"]}
    assert category_counts == {
        "category::Law": 9,
        "category::Policy": 6,
    }
