from relevance_tests import TestResult, generate_test_run_id, save_test_results_as_jsonl
from search.config import LABELS_PATH_STEM, TEST_RESULTS_DIR
from search.engines.duckdb import DuckDBLabelSearchEngine
from search.label import Label
from search.logging import get_logger
from search.testcase import FieldCharacteristicsTestCase, RecallTestCase

LabelTestResult = TestResult[Label]


logger = get_logger(__name__)

engines = [DuckDBLabelSearchEngine(db_path=LABELS_PATH_STEM.with_suffix(".duckdb"))]


test_cases = [
    RecallTestCase(
        search_terms="flood",
        expected_result_ids=["pdhcqueu"],
        description="search should find labels related to flood",
    ),
    FieldCharacteristicsTestCase(
        search_terms="nz",
        characteristics_test=lambda label: (
            "new zealand" in label.preferred_label.lower()
        )
        or ("net zero" in label.preferred_label.lower()),  # type: ignore
        all_or_any="all",
        description="search for nz should return either new zealand or net zero",
    ),
]


def test_labels():
    """Test labels"""

    for engine in engines:
        engine_test_results: list[LabelTestResult] = []

        for test_case in test_cases:
            test_passed, search_results = test_case.run_against(engine)

            test_result = LabelTestResult(
                test_case=test_case,
                passed=test_passed,
                search_engine_id=engine.id,
                search_results=search_results,
            )
            engine_test_results.append(test_result)

        test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
        output_file_path = (
            TEST_RESULTS_DIR / "labels" / f"{engine.name}_{test_run_id}.jsonl"
        )

        save_test_results_as_jsonl(engine_test_results, output_file_path)


if __name__ == "__main__":
    test_labels()
