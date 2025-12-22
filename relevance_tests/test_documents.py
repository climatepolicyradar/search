from relevance_tests import (
    TestResult,
    generate_test_run_id,
    print_test_results,
    save_test_results_as_jsonl,
)
from search.config import DOCUMENTS_PATH_STEM, TEST_RESULTS_DIR
from search.document import Document
from search.engines.duckdb import DuckDBDocumentSearchEngine
from search.logging import get_logger
from search.testcase import SearchComparisonTestCase

DocumentTestResult = TestResult[Document]


logger = get_logger(__name__)

engines = [
    DuckDBDocumentSearchEngine(db_path=DOCUMENTS_PATH_STEM.with_suffix(".duckdb"))
]

test_cases = [
    SearchComparisonTestCase[Document](
        category="duplicates",
        search_terms="obligation to provide renewable fuels 2005",
        search_terms_to_compare="obligation to provide renewable fuel 2005",
        description="Searches for single vs duplicate terms in a relatively long query should return the same top few documents",
        k=5,
        minimum_overlap=1.0,
        strict_order=False,
    ),
]


def test_documents():
    """Test documents"""

    for engine in engines:
        engine_test_results: list[DocumentTestResult] = []
        logger.info(f"Testing document test cases against {engine.name}")

        for test_case in test_cases:
            logger.info(
                f"Running test case: {test_case.name}: {test_case.search_terms}"
            )
            test_passed, search_results = test_case.run_against(engine)

            test_result = DocumentTestResult(
                test_case=test_case,
                passed=test_passed,
                search_engine_id=engine.id,
                search_results=search_results,
            )
            engine_test_results.append(test_result)

        print_test_results(engine_test_results)

        test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
        output_file_path = (
            TEST_RESULTS_DIR / "documents" / f"{engine.name}_{test_run_id}.jsonl"
        )

        save_test_results_as_jsonl(engine_test_results, output_file_path)


if __name__ == "__main__":
    test_documents()
