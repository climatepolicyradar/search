from pathlib import Path

import pytest

from search.engines import LabelSearchEngine
from search.engines.duckdb import DuckDBLabelSearchEngine
from search.testcase import TestCase


@pytest.fixture
def engine() -> LabelSearchEngine:
    """Create a search engine."""
    return DuckDBLabelSearchEngine(db_path=Path("data/labels.duckdb"))


@pytest.mark.parametrize(
    "test_case",
    [
        TestCase(
            search_terms="flood",
            expected_result_ids=["pdhcqueu"],
            description="search should find labels related to flood",
        )
    ],
)
def test_concepts(test_case: TestCase, engine: LabelSearchEngine) -> None:
    """Test the search engine's ability to find relevant results."""
    assert test_case.run_against(engine)
