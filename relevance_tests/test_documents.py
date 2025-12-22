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
from search.testcase import (
    FieldCharacteristicsTestCase,
    PrecisionTestCase,
    SearchComparisonTestCase,
    all_words_in_string,
)

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
    PrecisionTestCase[Document](
        category="punctuation",
        search_terms="Directive (EU) 2022/2464 amending Regulation (EU) No 537/2014 and others, as regards corporate sustainability reporting (Corporate Sustainability Reporting Directive or CSRD)",
        expected_result_ids=["buhkvq82"],
        description="Searching for a document title should return the correct document, where the title has brackets.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="obligation to provide renewable fuels 2005",
        expected_result_ids=["q7xu8hd9"],
        description="Searching for a document title where the words are in a different order.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="National Climate Change Strategy 2021-2026",
        expected_result_ids=["zkarxnpf"],
        description="Searching for the document title should return the correct document.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="fca rules of tcfd",
        expected_result_ids=["f3b2qeh6"],
        description="Acronyms in document titles",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="power up britain",
        expected_result_ids=["jcrp5cka", "dq5aty3a"],
        description="Stemmed words in document titles",
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="UK Climate Change Act",
        expected_result_ids=["dqk29nuc"],
        description="Searching for title + geography should return the correct document if geography is not in the document title (Climate Change Act 2008)",
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="energy policy act us",
        expected_result_ids=["p3rnnyee"],
        description="Searching for title + geography should return the correct document if geography is not in the document title (Energy Policy Act 2005 (Energy Bill))",
    ),
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="adaptation strategy",
        characteristics_test=lambda document: all_words_in_string(
            ["adaptation", "strategy"], document.title
        ),
        description="Search for 'Adaptation Strategy' should contain at least 20 adaptation strategies first.",
        k=20,
    ),
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="national communication",
        characteristics_test=lambda document: all_words_in_string(
            ["national", "communication"], document.title
        ),
        description="Search for 'National Communication' should contain at least 20 national communications first.",
        k=20,
    ),
    PrecisionTestCase[Document](
        category="document name",
        search_terms="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
        expected_result_ids=["872jfyqv"],
        description="Searching for exact law title should return the correct document",
    ),
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="national climate plan",
        characteristics_test=lambda document: all_words_in_string(
            ["national", "climate", "plan"], document.title
        ),
        description="Search for 'national climate plan' should return documents with that phrase in the title",
        k=10,
    ),
    PrecisionTestCase[Document](
        category="document name",
        search_terms="argentina LT-LEDS",
        expected_result_ids=["xjeh5fts"],
        description="Searching for 'argentina LT-LEDS' should return Argentina's long-term low greenhouse gas emission development strategy",
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name",
        search_terms="nz",
        characteristics_test=lambda document: any(
            term in document.title.lower() for term in ["nz", "new zealand", "net zero"]
        ),
        description="Search for 'nz' should return documents with 'nz', 'new zealand', or 'net zero' in the title",
        k=10,
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name",
        search_terms="juliana",
        characteristics_test=lambda document: "juliana" in document.title.lower(),
        description="Searching for 'juliana' should return cases with 'juliana' in the name",
        k=5,
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name",
        search_terms="milieudefensie",
        characteristics_test=lambda document: "milieudefensie"
        in document.title.lower(),
        description="Searching for 'milieudefensie' should return cases with 'milieudefensie' in the name",
        k=5,
    ),
    PrecisionTestCase[Document](
        category="BROKEN entity name",
        search_terms="Municipalities of Puerto Rico v. Exxon Mobil Corp.",
        # FIXME: need to fill in the ID once litigation is in the sample dataset
        expected_result_ids=[],
        description="Searching for 'Municipalities of Puerto Rico v. Exxon Mobil Corp.' should return case Commonwealth of Puerto Rico v. Exxon Mobil Corp.",
    ),
    FieldCharacteristicsTestCase[Document](
        category="BROKEN question",
        search_terms="what is the croatias climate strategy",
        characteristics_test=lambda document: all_words_in_string(
            ["climate", "strategy"], document.title
        )
        # FIXME: should use document metadata field here instead
        and any(
            term in document.title.lower() or term in document.description.lower()
            for term in ["croatia", "croatian"]
        ),
        description="Search for 'what is the croatias climate strategy' should return documents titled 'climate strategy' from with 'croatia' in the description. TODO: filter for croatia instead",
        k=5,
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
