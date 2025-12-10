from relevance_tests import TestResult
from search.config import LABELS_PATH_STEM
from search.engines.duckdb import DuckDBLabelSearchEngine
from search.engines.json import serialise_pydantic_list_as_jsonl
from search.label import Label
from search.logging import get_logger
from search.testcase import TestCase

LabelTestResult = TestResult[Label]


logger = get_logger(__name__)

engines = [DuckDBLabelSearchEngine(db_path=LABELS_PATH_STEM.with_suffix(".duckdb"))]


test_cases = [
    TestCase(
        search_terms="flood",
        expected_result_ids=["pdhcqueu"],
        description="search should find labels related to flood",
    )
]


def test_labels():
    """Test labels"""

    for engine in engines:
        engine_test_results: list[LabelTestResult] = []

        for test_case in test_cases:
            test_passed = test_case.run_against(engine)

            test_result = LabelTestResult(
                test_case=test_case,
                passed=test_passed,
                # search_engine_id=TODO
                search_results=[],  # TODO
            )
            engine_test_results.append(test_result)

        _ = serialise_pydantic_list_as_jsonl(engine_test_results)
        # TODO: save results to a file with a unique name based on an identifier of the engine and of the test results


if __name__ == "__main__":
    test_labels()
