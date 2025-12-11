import pytest

from search.engines import LabelSearchEngine
from search.engines.duckdb import DuckDBLabelSearchEngine
from search.label import Label
from search.testcase import TestCase


@pytest.fixture
def engine() -> LabelSearchEngine:
    """Create a search engine with test labels."""
    labels = [
        Label(
            preferred_label="flood",
            alternative_labels=["floods", "flooding", "inundation", "flooded"],
            negative_labels=[],
            description="Floods are the inundation of normally dry land, resulting from a mix of hydrology, climate, and huma\
n factors, varying by type and region.",
        ),
    ]
    return DuckDBLabelSearchEngine(items=labels)


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
