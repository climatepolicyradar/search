from relevance_tests import (
    TestResult,
    generate_test_run_id,
    print_test_results,
    save_test_results_as_jsonl,
)
from search.config import LABELS_PATH_STEM, TEST_RESULTS_DIR
from search.engines.duckdb import DuckDBLabelSearchEngine
from search.label import Label
from search.logging import get_logger
from search.testcase import (
    FieldCharacteristicsTestCase,
    PrecisionTestCase,
    RecallTestCase,
)

LabelTestResult = TestResult[Label]


logger = get_logger(__name__)

engines = [DuckDBLabelSearchEngine(db_path=LABELS_PATH_STEM.with_suffix(".duckdb"))]


test_cases = [
    PrecisionTestCase[Label](
        category="place name",
        search_terms="brazil",
        expected_result_ids=["TODOBRAZIL"],
        description="search for brazil should return correct label first",
    ),
    PrecisionTestCase[Label](
        category="place name",
        search_terms="new south wales",
        expected_result_ids=["TODONEWSOUTHWALES", "TODOAUSTRALIA"],
        description="search for new south wales should return new south wales and australia",
    ),
    PrecisionTestCase[Label](
        category="place name + other terms",
        search_terms="Philippines policies in climate changes",
        expected_result_ids=[
            "TODOPHILIPPINES",
            "TODOPOLICIES",
            "TODOCLIMATE",
        ],
        description="search for philippines policies in climate changes should return relevant labels first",
    ),
    RecallTestCase[Label](
        category="place name + other terms",
        search_terms="brazil nature based solutions",
        expected_result_ids=["TODOBRAZIL"],
        k=3,
        description="search for brazil nature based solutions should return brazil label in the top 3 results",
    ),
    # NOTE: this test has been left as a FieldCharacteristicsTestCase rather than using
    # IDs, because we have lots of energy-related concepts but one specifically for
    # 'energy'. I.e. we want to test for concepts that have 'energy' in them.
    FieldCharacteristicsTestCase[Label](
        category="document name",
        search_terms="energy policy act us",
        characteristics_test=lambda label: (
            "energy" in label.preferred_label.lower()
            or "policy" in label.preferred_label.lower()
            or "usa" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for energy policy act us should return relevant labels",
    ),
    RecallTestCase[Label](
        category="document name",
        search_terms="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
        expected_result_ids=["TODOLAW", "TODOCLIMATE"],
        k=3,
        description="search for law relating to climate change should return laws or climate labels",
    ),
    PrecisionTestCase[Label](
        category="document name",
        search_terms="national climate plan",
        expected_result_ids=["TODONATIONAL", "TODOCLIMATE", "TODOPLAN"],
        description="search for national climate plan should return relevant labels first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="nz",
        expected_result_ids=[
            "wpx36e4m",  # net-zero target
            "TODONEWZEALAND",
        ],
        description="search for nz should return 'new zealand' and 'net zero target' first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="totalenergies",
        expected_result_ids=["TODOTOTAL_ENERGIES"],
        description="search for totalenergies should return total energies label first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="european court of human rights",
        expected_result_ids=["TODOECHR"],
        description="search for european court of human rights should return matching label first",
    ),
    PrecisionTestCase[Label](
        category="question",
        search_terms="How many targets does Canada currently have relating to climate change?",
        expected_result_ids=[
            "sk4kv7u3",  # target
            "TODOCANADA",
            "TODOCLIMATE",
        ],
        description="search about canada targets should return relevant labels first",
    ),
    PrecisionTestCase[Label](
        category="question",
        search_terms="what is the croatias climate strategy",
        expected_result_ids=[
            "wf4tcvtp",  # strategy setting and planning
            "TODOCLIMATE",
            "TODOPOLICY",
            "TODOSTRATEGY",
        ],
        description="search about croatia climate strategy should return relevant labels first",
    ),
    RecallTestCase[Label](
        category="topic",
        search_terms="hurricanes",
        expected_result_ids=[
            "rvw4bbqe",  # extreme weather
            "6etq43sc",  # storm
        ],
        k=5,
        description="search for hurricanes should return 'extreme weather' and 'storm' labels in the top 5 results",
    ),
    PrecisionTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        expected_result_ids=[
            "guaj3bdu",  # removal of fossil fuel subsidy
        ],
        description="search for fossil fuel subsidy removal should return 'removal of fossil fuel subsidy' label first",
    ),
    RecallTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        expected_result_ids=[
            "pnsjhvgp",  # subsidy removal
        ],
        forbidden_result_ids=[
            "bg8bf2cs",  # subsidy
        ],
        k=10,
        description="search for fossil fuel subsidy removal should return 'subsidy removal' label, and NOT 'subsidy' label",
    ),
    PrecisionTestCase[Label](
        category="topic",
        search_terms="Just transition",
        expected_result_ids=[
            "fyujvkcc",  # just transition
        ],
        description="search for just transition should return just transition label first",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="resilient infrastructure",
        characteristics_test=lambda label: (
            "resilient" in label.preferred_label.lower()
            or "infrastructure" in label.preferred_label.lower()
            or "construction" in label.preferred_label.lower()
        ),
        all_or_any="any",
        description="search for resilient infrastructure should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="offshore wind roadmap",
        characteristics_test=lambda label: (
            "wind" in label.preferred_label.lower()
            or "energy" in label.preferred_label.lower()
        ),
        all_or_any="any",
        description="search for offshore wind roadmap should return wind energy labels",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="Adaptation (OR) resilience investment",
        expected_result_ids=[
            "qz6fg4dh",  # adaptation finance
        ],
        description="search for adaptation or resilience investment should return adaptation finance label first",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="japan + united states + sweden + china",
        expected_result_ids=[
            "TODOJAPAN",  # japan
            "TODOUSA",  # united states/us
            "TODOSWEDEN",  # sweden
            "TODOCHINA",  # china
        ],
        description="search for multiple countries should return labels for those countries first",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="indigenous people + colombia + laws",
        expected_result_ids=[
            "ptfmpyqe",  # indigenous people
            "6cn2vjae",  # impacted group
            "TODOCOLOMBIA",  # colombia
            "TODOLAWS",  # laws
        ],
        description="search for indigenous people colombia laws should return relevant labels first",
    ),
    FieldCharacteristicsTestCase[Label](
        category="entity name",
        search_terms="totalenergies",
        characteristics_test=lambda label: (
            "total" in label.preferred_label.lower()
            and "energies" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for totalenergies should return total energies label",
    ),
    FieldCharacteristicsTestCase[Label](
        category="entity name",
        search_terms="european court of human rights",
        characteristics_test=lambda label: (
            "european" in label.preferred_label.lower()
            and "court" in label.preferred_label.lower()
            and "human" in label.preferred_label.lower()
            and "rights" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for european court of human rights should return matching label",
    ),
    FieldCharacteristicsTestCase[Label](
        category="question",
        search_terms="How many targets does Canada currently have relating to climate change?",
        characteristics_test=lambda label: (
            "targets" in label.preferred_label.lower()
            or "canada" in label.preferred_label.lower()
            or "climate" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search about canada targets should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="question",
        search_terms="what is the croatias climate strategy",
        characteristics_test=lambda label: (
            "croatia" in label.preferred_label.lower()
            or "climate" in label.preferred_label.lower()
            or "policy" in label.preferred_label.lower()
            or "strategy" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search about croatia climate strategy should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="hurricanes",
        characteristics_test=lambda label: (
            "extreme weather" in label.preferred_label.lower()
            or "storm" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for hurricanes should return extreme weather or storm related labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        characteristics_test=lambda label: (
            (
                "fossil" in label.preferred_label.lower()
                and "fuel" in label.preferred_label.lower()
            )
            or (
                "subsidy" in label.preferred_label.lower()
                and "removal" in label.preferred_label.lower()
            )
        ),
        all_or_any="all",
        description="search for fossil fuel subsidy removal should return fossil fuel or subsidy removal related labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        characteristics_test=lambda label: (label.preferred_label.lower() != "subsidy"),
        all_or_any="all",
        description="search for fossil fuel subsidy removal should not return subsidy labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="Just transition",
        characteristics_test=lambda label: (
            label.preferred_label.lower() == "just transition"
        ),
        all_or_any="any",
        description="search for just transition should return just transition label",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="resilient infrastructure",
        characteristics_test=lambda label: (
            "resilient" in label.preferred_label.lower()
            or "infrastructure" in label.preferred_label.lower()
            or "construction" in label.preferred_label.lower()
        ),
        all_or_any="any",
        description="search for resilient infrastructure should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="offshore wind roadmap",
        characteristics_test=lambda label: (
            "wind" in label.preferred_label.lower()
            or "energy" in label.preferred_label.lower()
        ),
        all_or_any="any",
        description="search for offshore wind roadmap should return wind energy labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="logic",
        search_terms="Adaptation (OR) resilience investment",
        characteristics_test=lambda label: (
            label.preferred_label.lower() == "adaptation finance"
        ),
        all_or_any="any",
        description="search for adaptation or resilience investment should return adaptation finance labels",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Label](
        category="logic",
        search_terms="japan + united states + sweden + china",
        characteristics_test=lambda label: (
            "japan" in label.preferred_label.lower()
            or "us" in label.preferred_label.lower()
            or "united states" in label.preferred_label.lower()
            or "sweden" in label.preferred_label.lower()
            or "china" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for multiple countries should return labels for those countries",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Label](
        category="logic",
        search_terms="indigenous people + colombia + laws",
        characteristics_test=lambda label: (
            "indigenous" in label.preferred_label.lower()
            or label.preferred_label.lower() == "impacted groups"
            or "colombia" in label.preferred_label.lower()
            or "laws" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for indigenous people colombia laws should return relevant labels",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Label](
        category="entity name",
        search_terms="totalenergies",
        characteristics_test=lambda label: (
            "total" in label.preferred_label.lower()
            and "energies" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for totalenergies should return total energies label",
    ),
    FieldCharacteristicsTestCase[Label](
        category="entity name",
        search_terms="european court of human rights",
        characteristics_test=lambda label: (
            "european" in label.preferred_label.lower()
            and "court" in label.preferred_label.lower()
            and "human" in label.preferred_label.lower()
            and "rights" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for european court of human rights should return matching label",
    ),
    FieldCharacteristicsTestCase[Label](
        category="question",
        search_terms="How many targets does Canada currently have relating to climate change?",
        characteristics_test=lambda label: (
            "targets" in label.preferred_label.lower()
            or "canada" in label.preferred_label.lower()
            or "climate" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search about canada targets should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="question",
        search_terms="what is the croatias climate strategy",
        characteristics_test=lambda label: (
            "croatia" in label.preferred_label.lower()
            or "climate" in label.preferred_label.lower()
            or "policy" in label.preferred_label.lower()
            or "strategy" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search about croatia climate strategy should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="hurricanes",
        characteristics_test=lambda label: (
            "extreme weather" in label.preferred_label.lower()
            or "storm" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for hurricanes should return extreme weather or storm related labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        characteristics_test=lambda label: (
            (
                "fossil" in label.preferred_label.lower()
                and "fuel" in label.preferred_label.lower()
            )
            or (
                "subsidy" in label.preferred_label.lower()
                and "removal" in label.preferred_label.lower()
            )
        ),
        all_or_any="all",
        description="search for fossil fuel subsidy removal should return fossil fuel or subsidy removal related labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        characteristics_test=lambda label: (label.preferred_label.lower() != "subsidy"),
        all_or_any="all",
        description="search for fossil fuel subsidy removal should not return subsidy labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic",
        search_terms="Just transition",
        characteristics_test=lambda label: (
            label.preferred_label.lower() == "just transition"
        ),
        all_or_any="any",
        description="search for just transition should return just transition label",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="resilient infrastructure",
        characteristics_test=lambda label: (
            "resilient" in label.preferred_label.lower()
            or "infrastructure" in label.preferred_label.lower()
            or "construction" in label.preferred_label.lower()
        ),
        all_or_any="any",
        description="search for resilient infrastructure should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="offshore wind roadmap",
        characteristics_test=lambda label: (
            "wind" in label.preferred_label.lower()
            or "energy" in label.preferred_label.lower()
        ),
        all_or_any="any",
        description="search for offshore wind roadmap should return wind energy labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="logic",
        search_terms="Adaptation (OR) resilience investment",
        characteristics_test=lambda label: (
            label.preferred_label.lower() == "adaptation finance"
        ),
        all_or_any="any",
        description="search for adaptation or resilience investment should return adaptation finance labels",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Label](
        category="logic",
        search_terms="japan + united states + sweden + china",
        characteristics_test=lambda label: (
            "japan" in label.preferred_label.lower()
            or "us" in label.preferred_label.lower()
            or "united states" in label.preferred_label.lower()
            or "sweden" in label.preferred_label.lower()
            or "china" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for multiple countries should return labels for those countries",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Label](
        category="logic",
        search_terms="indigenous people + colombia + laws",
        characteristics_test=lambda label: (
            "indigenous" in label.preferred_label.lower()
            or label.preferred_label.lower() == "impacted groups"
            or "colombia" in label.preferred_label.lower()
            or "laws" in label.preferred_label.lower()
        ),
        all_or_any="all",
        description="search for indigenous people colombia laws should return relevant labels",
        assert_results=True,
    ),
]


def test_labels():
    """Test labels"""

    for engine in engines:
        engine_test_results: list[LabelTestResult] = []
        logger.info(f"Testing label test cases against {engine.name}")
        for test_case in test_cases:
            logger.info(
                f"Running test case: {test_case.name}: {test_case.search_terms}"
            )
            test_passed, search_results = test_case.run_against(engine)

            test_result = LabelTestResult(
                test_case=test_case,
                passed=test_passed,
                search_engine_id=engine.id,
                search_results=search_results,
            )
            engine_test_results.append(test_result)

        print_test_results(engine_test_results)

        test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
        output_file_path = (
            TEST_RESULTS_DIR / "labels" / f"{engine.name}_{test_run_id}.jsonl"
        )

        save_test_results_as_jsonl(engine_test_results, output_file_path)


if __name__ == "__main__":
    test_labels()
