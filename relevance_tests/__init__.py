from pathlib import Path
from typing import Generic, TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel

from search.engines import SearchEngine
from search.engines.json import serialise_pydantic_list_as_jsonl
from search.logging import get_logger
from search.testcase import TestCase

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class TestResult(BaseModel, Generic[T]):
    """A result of a test-case run against a search engine"""

    test_case: TestCase
    passed: bool
    search_engine_id: Identifier
    search_results: list[T]


def save_test_results_as_jsonl(test_results: list[TestResult], file_path: Path) -> None:
    """Save test results to a JSONL file"""

    jsonl_results = serialise_pydantic_list_as_jsonl(test_results)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(jsonl_results)
    logger.info(f"Saved test results to {file_path}")


def generate_test_run_id(
    engine: SearchEngine, test_cases: list[TestCase], test_results: list[TestResult]
) -> Identifier:
    """Generate a unique identifier for a test run"""

    test_run_id = Identifier.generate(engine.name, *test_cases, *test_results)
    logger.info(f"Generated test run id: {test_run_id}")
    return test_run_id
