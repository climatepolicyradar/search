"""Tests for relevance tests."""

import pytest
from knowledge_graph.identifiers import Identifier

from relevance_tests import TestResult, generate_test_run_id

pytest.fixture()


def get_mock_search_engine():
    class MockEngine:
        @property
        def name(self):
            return "JSONLabelSearchEngine"

    return MockEngine()


def test_generate_test_run_id_is_deterministic(
    simple_test_case, simple_test_result, test_labels
):
    """Test that generate_test_run_id produces the same ID for identical inputs."""

    engine = get_mock_search_engine()
    test_cases = [simple_test_case]
    test_results = [simple_test_result]

    id1 = generate_test_run_id(engine, test_cases, test_results)  # type: ignore
    id2 = generate_test_run_id(engine, test_cases, test_results)  # type: ignore

    assert id1 == id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


def test_generate_test_run_id_changes_when_test_case_changes(
    simple_test_case, another_test_case, simple_test_result
):
    """Test that generate_test_run_id produces different IDs when test cases change."""

    engine = get_mock_search_engine()

    test_results = [simple_test_result]

    id1 = generate_test_run_id(engine, [simple_test_case], test_results)  # type: ignore
    id2 = generate_test_run_id(engine, [another_test_case], test_results)  # type: ignore

    assert id1 != id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


def test_generate_test_run_id_changes_when_test_result_changes(
    simple_test_case, simple_test_result, test_labels
):
    """Test that generate_test_run_id produces different IDs when test results change."""

    engine = get_mock_search_engine()
    test_cases = [simple_test_case]

    id1 = generate_test_run_id(engine, test_cases, [simple_test_result])  # type: ignore

    modified_test_result = TestResult(
        test_case=simple_test_result.test_case,
        passed=False,  # Changed from True to False
        search_engine_id=simple_test_result.search_engine_id,
        search_results=simple_test_result.search_results,
    )
    id2 = generate_test_run_id(engine, test_cases, [modified_test_result])  # type: ignore

    assert id1 != id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


def test_generate_test_run_id_changes_when_engine_changes(
    simple_test_case, simple_test_result
):
    """Test that generate_test_run_id produces different IDs when the engine changes."""

    class JSONEngine:
        @property
        def name(self):
            return "JSONLabelSearchEngine"

    class DuckDBEngine:
        @property
        def name(self):
            return "DuckDBLabelSearchEngine"

    json_engine = JSONEngine()
    duckdb_engine = DuckDBEngine()

    test_cases = [simple_test_case]
    test_results = [simple_test_result]

    id1 = generate_test_run_id(json_engine, test_cases, test_results)  # type: ignore
    id2 = generate_test_run_id(duckdb_engine, test_cases, test_results)  # type: ignore

    assert id1 != id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)
