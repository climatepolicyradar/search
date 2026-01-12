from relevance_tests import (
    TestResult,
    generate_test_run_id,
    print_test_results,
    save_test_results_as_jsonl,
)
from search.config import PASSAGES_PATH_STEM, TEST_RESULTS_DIR
from search.engines.duckdb import DuckDBPassageSearchEngine
from search.log import get_logger
from search.passage import Passage
from search.testcase import (
    FieldCharacteristicsTestCase,
    SearchComparisonTestCase,
    all_words_in_string,
    any_words_in_string,
)
from search.weights_and_biases import WandbSession

PassageTestResult = TestResult[Passage]


logger = get_logger(__name__)

engines = [DuckDBPassageSearchEngine(db_path=PASSAGES_PATH_STEM.with_suffix(".duckdb"))]

test_cases = [
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="nz",
        characteristics_test=lambda passage: ("new zealand" in passage.text.lower())
        or ("net zero" in passage.text.lower()),  # type: ignore
        all_or_any="all",
        description="search for nz should return either new zealand or net zero in the passage text",
    ),
    SearchComparisonTestCase[Passage](
        category="duplicates",
        search_terms="solar power",
        search_terms_to_compare="solar powered",
        description="Compare single vs duplicated search terms (solar power vs solar powered).",
        k=50,
        minimum_overlap=0.8,
        strict_order=False,
    ),
    SearchComparisonTestCase[Passage](
        category="duplicates",
        search_terms="citizen assembly",
        search_terms_to_compare="citizens assembly",
        description="Compare single vs duplicated search terms (citizen assembly vs citizens assembly).",
        k=50,
        minimum_overlap=0.8,
        strict_order=False,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="search term + geography",
        search_terms="brazil nature based solutions",
        characteristics_test=lambda passage: "nature based solutions"
        in passage.text.lower().replace("-", " "),
        all_or_any="any",
        description="Search for 'brazil nature based solutions' returns passages which mention nature based solutions",
    ),
    FieldCharacteristicsTestCase[Passage](
        category="exact match",
        search_terms='"national strategy for climate change 2050"',
        characteristics_test=lambda passage: "national strategy for climate change 2050"
        in passage.text.lower(),
        description="Search in quotes should perform an exact match search.",
        k=100,
        all_or_any="all",
    ),
    FieldCharacteristicsTestCase[Passage](
        category="BROKEN exact match",
        search_terms="adaptation options",
        # FIXME: this tests exact match search, which we don't currently consider using these tests
        # exact_match=True,
        characteristics_test=(
            lambda passage: not (
                "adaptation option" in passage.text.lower()
                and "adaptation options" not in passage.text.lower()
            )
        ),
        description="Exact match search should not perform stemming.",
        k=100,
        all_or_any="all",
    ),
    FieldCharacteristicsTestCase[Passage](
        category="dissimilar passages excluded",
        search_terms="mango",
        characteristics_test=(lambda passage: "mango" in passage.text.lower()),
        description="Dissimilar passages to 'mango' should be excluded.",
        k=20,
        all_or_any="all",
    ),
    FieldCharacteristicsTestCase[Passage](
        category="dissimilar passages excluded",
        search_terms="statement",
        characteristics_test=(lambda passage: "statement" in passage.text.lower()),
        description="Dissimilar passages to 'statement' should be excluded.",
        k=20,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="punctuation",
        search_terms="$100",
        characteristics_test=lambda passage: any(
            phrase in passage.text
            for phrase in ["$100", "$ 100", "100 dollars", "100 USD"]
        ),
        description="Search for $100 should always return $100.",
        k=100,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="punctuation",
        search_terms="$100",
        characteristics_test=lambda passage: not (
            "$1000" in passage.text and "$100" not in passage.text
        ),
        description="Exact match search for $100 should not return $1000.",
        k=100,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="nationally determined contribution",
        characteristics_test=lambda passage: "NDC" in passage.text
        and not all_words_in_string(
            ["nationally", "determined", "contribution"], passage.text
        ),
        description="Acronyms: search for nationally determined contribution should return NDC.",
        k=100,
        all_or_any="any",
    ),
    FieldCharacteristicsTestCase[Passage](
        category="misspellings",
        search_terms="environment",
        characteristics_test=lambda passage: all_words_in_string(
            ["environment"], passage.text
        ),
        description="Search for misspelled text (environment).",
        k=20,
        all_or_any="any",
    ),
    FieldCharacteristicsTestCase[Passage](
        category="logic",
        search_terms="green-washing or greenwashing or climatewashing or climate-washing",
        characteristics_test=lambda passage: any_words_in_string(
            ["greenwashing", "green-washing", "climatewashing", "climate-washing"],
            passage.text,
        ),
        description="OR logic in search.",
        k=20,
        all_or_any="all",
    ),
]


def test_passages():
    """Test passages"""

    wb = WandbSession()

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

        print_test_results(engine_test_results)
        wb.log_test_results(
            test_results=engine_test_results,
            primitive=Passage,
        )

        test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
        output_file_path = (
            TEST_RESULTS_DIR / "passages" / f"{engine.name}_{test_run_id}.jsonl"
        )

        save_test_results_as_jsonl(engine_test_results, output_file_path)


if __name__ == "__main__":
    test_passages()
