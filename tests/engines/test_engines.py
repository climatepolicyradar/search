"""Shared tests for all search engine implementations."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from search import Primitive
from search.engines import SearchEngine
from tests.engines import get_valid_search_term


class TestSearchBehavior:
    def test_whether_search_returns_correct_type(
        self,
        any_engine_and_items: tuple[SearchEngine, list[Primitive]],
    ):
        engine, items = any_engine_and_items
        search_term = get_valid_search_term(items[0])

        results = engine.search(search_term)
        assert isinstance(results, list)
        assert all(isinstance(r, engine.model_class) for r in results)

    def test_whether_search_returns_empty_for_nonexistent_term(self, any_engine):
        search_terms_which_almost_definitely_wont_match = "xyzabc123nonexistent"
        results = any_engine.search(search_terms_which_almost_definitely_wont_match)
        assert results == []

    @given(search_term=st.text(min_size=0, max_size=100))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_whether_search_handles_arbitrary_input(
        self, any_engine: SearchEngine, search_term: str
    ):
        """Make sure search doesn't blow up when given weird strings by hypothesis."""
        results = any_engine.search(search_term)
        assert isinstance(results, list)

    def test_whether_search_results_are_deterministic(
        self,
        any_engine_and_items: tuple[SearchEngine, list[Primitive]],
    ):
        engine, items = any_engine_and_items
        search_term = get_valid_search_term(items[0])[:10]

        results_1 = engine.search(search_term)
        results_2 = engine.search(search_term)

        assert {r.id for r in results_1} == {r.id for r in results_2}
