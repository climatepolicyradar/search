from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel, field_validator

from search.engines import SearchEngine


class TestCase(BaseModel):
    """A test case"""

    __test__ = False

    search_terms: str
    expected_result_ids: list[Identifier | str]
    description: str

    @field_validator("expected_result_ids", mode="before")
    @classmethod
    def coerce_identifiers(cls, value: list[str | Identifier]) -> list[Identifier]:
        """
        Coerce string identifiers to Identifier objects.

        This validator allows strings to be passed in to `expected_result_ids`.
        """
        return [Identifier(item) if isinstance(item, str) else item for item in value]

    def run_against(self, engine: SearchEngine) -> bool:
        """Run the test case against the given engine."""
        search_results = engine.search(self.search_terms)
        result_ids = [result.id for result in search_results]
        return all(
            expected_id in result_ids for expected_id in self.expected_result_ids
        )
