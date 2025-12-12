from typing import TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel, field_validator

from search.document import Document
from search.engines import SearchEngine
from search.label import Label
from search.passage import Passage

TModel = TypeVar("TModel", Label, Passage, Document)


class TestCase(BaseModel):
    """A test case"""

    __test__ = False

    category: str | None = None
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

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        """Normalize category: convert to lowercase with underscores."""
        if value is None:
            return value
        return value.strip().lower().replace("-", "_").replace(" ", "_")

    def run_against(self, engine: SearchEngine) -> tuple[bool, list[TModel]]:
        """Run the test case against the given engine."""
        search_results = engine.search(self.search_terms)
        result_ids = [result.id for result in search_results]
        return (
            all(expected_id in result_ids for expected_id in self.expected_result_ids),
            search_results,
        )
