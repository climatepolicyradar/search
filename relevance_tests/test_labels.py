from prefect.task_runners import ThreadPoolTaskRunner

from api.dev import settings
from prefect import flow
from relevance_tests import run_relevance_tests_parallel
from search.engines.dev_vespa import (
    DevVespaLabelSearchEngine,
)
from search.label import Label
from search.testcase import (
    FieldCharacteristicsTestCase,
    PrecisionTestCase,
    RecallTestCase,
)

test_cases = [
    PrecisionTestCase[Label](
        category="place name",
        search_terms="brazil",
        expected_result_ids=["geography::BRA"],  # BRAZIL
        description="search for brazil should return correct label first",
    ),
    PrecisionTestCase[Label](
        category="place name",
        search_terms="new south wales",
        expected_result_ids=[
            "geography::AUS",
            "geography::AU-NSW",
        ],  # NEW SOUTH WALES, AUSTRALIA
        description="search for new south wales should return new south wales and australia",
    ),
    PrecisionTestCase[Label](
        category="place name + other terms",
        search_terms="Philippines policies in climate changes",
        expected_result_ids=[
            "geography::PHL",  # PHILIPPINES
            "entity_type::Policy",  # POLICY
            # "dummy996",  # CLIMATE
        ],
        description="search for philippines policies in climate changes should return relevant labels first",
    ),
    RecallTestCase[Label](
        category="place name + other terms",
        search_terms="brazil nature based solutions",
        expected_result_ids=["geography::BRA"],  # BRAZIL
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
            "energy" in label.value.lower()
            or "polic" in label.value.lower()
            or "act" in label.value.lower()
            or "usa" in label.value.lower()
        ),
        all_or_any="all",
        description="search for energy policy act us should return relevant labels",
        k=10,
    ),
    RecallTestCase[Label](
        category="document name",
        search_terms="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
        expected_result_ids=[
            "entity_type::Law",  # LAW
            # "dummy996" # CLIMATE
        ],
        k=3,
        description="search for law relating to climate change should return laws or climate labels",
    ),
    PrecisionTestCase[Label](
        category="document name",
        search_terms="national climate plan",
        # Not so sure about this one. There might be a few labels that are relevant
        # but not included eg "law and plan"
        expected_result_ids=[
            "entity_type::Nationally determined contribution",
            "entity_type::National adaptation plan",
            "entity_type::National drought plan (ndp)",
            "entity_type::National biodiversity strategy and action plan (nbsap)",
            "entity_type::National target (nt)",
            "entity_type::Plan",
        ],
        description="search for national climate plan should return relevant document types first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="nz",
        expected_result_ids=[
            "concept::Q1653",  # net-zero target
            "geography::NZL",  # NEW ZEALAND
        ],
        description="search for nz should return 'new zealand' and 'net zero target' first",
    ),
    # PrecisionTestCase[Label](
    #     category="entity name",
    #     search_terms="totalenergies",
    #     expected_result_ids=["dummy933"],  # TOTAL ENERGIES
    #     description="search for totalenergies should return total energies label first",
    # ),
    # PrecisionTestCase[Label](
    #     category="entity name",
    #     search_terms="european court of human rights",
    #     expected_result_ids=["dummy932"],  # ECHR
    #     description="search for european court of human rights should return matching label first",
    # ),
    PrecisionTestCase[Label](
        category="question",
        search_terms="How many targets does Canada currently have relating to climate change?",
        expected_result_ids=[
            "concept::Q1651",  # target
            "geography::CAN",  # CANADA
            # "dummy996",  # CLIMATE
        ],
        description="search about canada targets should return relevant labels first",
    ),
    PrecisionTestCase[Label](
        category="question",
        search_terms="what is the croatias climate strategy",
        expected_result_ids=[
            # "wf4tcvtp",  # strategy setting and planning
            # "dummy996",  # CLIMATE
            "entity_type::Policy",  # POLICY
            "entity_type::Strategy",  # STRATEGY
            "geography::HRV",  # Croatia
        ],
        description="search about croatia climate strategy should return relevant labels first",
    ),
    RecallTestCase[Label](
        category="topic",
        search_terms="hurricanes",
        expected_result_ids=[
            "concept::Q374",  # extreme weather
            # "6etq43sc",  # storm (we don't have a classifier for this)
        ],
        k=5,
        description="search for hurricanes should return 'extreme weather' and 'storm' labels in the top 5 results",
    ),
    PrecisionTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        expected_result_ids=[
            "concept::Q638",  # fossil fuel
            "concept::Q1275",  # subsidy removal
        ],
        description="search for fossil fuel subsidy removal should return 'fossil fuel' and 'subsidy removal' labels first",
    ),
    RecallTestCase[Label](
        category="topic",
        search_terms="fossil fuel subsidy removal",
        expected_result_ids=[
            "concept::Q1275",  # subsidy removal
        ],
        forbidden_result_ids=[
            "concept::Q1274",  # subsidy
        ],
        k=10,
        description="search for fossil fuel subsidy removal should return 'subsidy removal' label, and NOT 'subsidy' label",
    ),
    PrecisionTestCase[Label](
        category="topic",
        search_terms="Just transition",
        expected_result_ids=[
            "concept::Q47",  # just transition
        ],
        description="search for just transition should return just transition label first",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="resilient infrastructure",
        characteristics_test=lambda label: (
            "resilient" in label.value.lower()
            or "infrastructure" in label.value.lower()
            or "construction" in label.value.lower()
        ),
        all_or_any="any",
        description="search for resilient infrastructure should return relevant labels",
    ),
    FieldCharacteristicsTestCase[Label](
        category="topic not in kg",
        search_terms="offshore wind roadmap",
        characteristics_test=lambda label: (
            "wind" in label.value.lower() or "energy" in label.value.lower()
        ),
        all_or_any="any",
        description="search for offshore wind roadmap should return wind energy labels",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="Adaptation (OR) resilience investment",
        expected_result_ids=[
            "concept::Q1345",  # adaptation finance
        ],
        description="search for adaptation or resilience investment should return adaptation finance label first",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="japan + united states + sweden + china",
        expected_result_ids=[
            "geography::JPN",
            "geography::USA",
            "geography::SWE",
            "geography::CHN",
        ],
        description="search for multiple countries should return labels for those countries first",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="indigenous people + colombia + laws",
        expected_result_ids=[
            "concept::Q684",  # indigenous people
            "geography::COL",  # COLOMBIA
            "entity_type::Law",
        ],
        description="search for indigenous people colombia laws should return relevant labels first",
    ),
]


@flow(
    name="relevance_tests_labels",
    task_runner=ThreadPoolTaskRunner(max_workers=3),  # type: ignore[arg-type]
)
def relevance_tests_labels():
    """Run relevance tests for labels"""

    engines = [
        DevVespaLabelSearchEngine(settings=settings),
        # DevVespaLabelTypeaheadSearchEngine(),
        # VespaLabelSearchEngine(),
    ]

    run_relevance_tests_parallel(
        engines=engines,
        test_cases=test_cases,
        primitive_type=Label,
        output_subdir="labels",
    )


if __name__ == "__main__":
    relevance_tests_labels()
