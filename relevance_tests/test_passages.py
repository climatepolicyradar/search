from relevance_tests import TestResult, generate_test_run_id, save_test_results_as_jsonl
from search.config import PASSAGES_PATH_STEM, TEST_RESULTS_DIR
from search.engines.duckdb import DuckDBPassageSearchEngine
from search.logging import get_logger
from search.passage import Passage
from search.testcase import FieldCharacteristicsTestCase, RecallTestCase

PassageTestResult = TestResult[Passage]


logger = get_logger(__name__)

engines = [DuckDBPassageSearchEngine(db_path=PASSAGES_PATH_STEM.with_suffix(".duckdb"))]

# TODO: Add proper test cases for passages
test_cases = [
    RecallTestCase[Passage](
        search_terms="flood",
        expected_result_ids=["pdhcqueu"],
        description="search should find passages related to flood",
    ),
    FieldCharacteristicsTestCase[Passage](
        search_terms="nz",
        characteristics_test=lambda passage: ("new zealand" in passage.text.lower())
        or ("net zero" in passage.text.lower()),  # type: ignore
        all_or_any="all",
        description="search for nz should return either new zealand or net zero in the passage text",
    ),
]


def test_passages():
    """Test passages"""

    for engine in engines:
        engine_test_results: list[PassageTestResult] = []
        logger.info(f"Testing passage test cases against {engine.name}")
        for test_case in test_cases:
            logger.info(
                f"Running test case: {test_case.name}: {test_case.search_terms}"
            )
            test_passed, search_results = test_case.run_against(engine)

            test_result = PassageTestResult(
                test_case=test_case,
                passed=test_passed,
                search_engine_id=engine.id,
                search_results=search_results,
            )
            engine_test_results.append(test_result)

        test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
        output_file_path = (
            TEST_RESULTS_DIR / "passages" / f"{engine.name}_{test_run_id}.jsonl"
        )

        save_test_results_as_jsonl(engine_test_results, output_file_path)


if __name__ == "__main__":
    test_passages()
