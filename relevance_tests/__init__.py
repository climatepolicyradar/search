from typing import Generic, TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel

from search.testcase import TestCase

T = TypeVar("T", bound=BaseModel)


class TestResult(BaseModel, Generic[T]):
    """A result of a test-case run against a search engine"""

    test_case: TestCase
    passed: bool
    search_engine_id: Identifier | None = None  # FIXME: populate this
    search_results: list[T]
