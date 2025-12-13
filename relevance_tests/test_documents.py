from relevance_tests import TestResult, generate_test_run_id, save_test_results_as_jsonl
from search.config import DOCUMENTS_PATH_STEM, TEST_RESULTS_DIR
from search.document import Document
from search.engines.duckdb import DuckDBDocumentSearchEngine
from search.logging import get_logger
from search.testcase import FieldCharacteristicsTestCase, RecallTestCase

DocumentTestResult = TestResult[Document]


logger = get_logger(__name__)

engines = [
    DuckDBDocumentSearchEngine(db_path=DOCUMENTS_PATH_STEM.with_suffix(".duckdb"))
]

# TODO: Add proper test cases for documents
test_cases = [
    RecallTestCase(
        search_terms="flood",
        expected_result_ids=["pdhcqueu"],
        description="search should find documents related to flood",
    ),
    FieldCharacteristicsTestCase(
        search_terms="nz",
        characteristics_test=lambda document: ("new zealand" in document.title.lower())
        or ("net zero" in document.title.lower()),  # type: ignore
        all_or_any="all",
        description="search for nz should return either new zealand or net zero in the document title",
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

        test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
        output_file_path = (
            TEST_RESULTS_DIR / "documents" / f"{engine.name}_{test_run_id}.jsonl"
        )

        save_test_results_as_jsonl(engine_test_results, output_file_path)


if __name__ == "__main__":
    test_documents()
