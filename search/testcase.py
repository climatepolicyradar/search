from pydantic import BaseModel

from search.engines import SearchEngine
from search.identifier import Identifier


class TestCase(BaseModel):
    """A test case"""

    search_terms: str
    expected_result_ids: list[Identifier]
    description: str

    def run_against(self, engine: SearchEngine) -> bool:
        """Run the test case against the given engine."""
        search_results = engine.search(self.search_terms)
        result_ids = [result.id for result in search_results]
        return all(
            expected_id in result_ids for expected_id in self.expected_result_ids
        )
