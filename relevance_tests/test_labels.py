from prefect import flow, get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner

from relevance_tests import run_relevance_tests_parallel
from search.engines.vespa import VespaLabelSearchEngine
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
        expected_result_ids=["dummy922"],  # BRAZIL
        description="search for brazil should return correct label first",
    ),
    PrecisionTestCase[Label](
        category="place name",
        search_terms="new south wales",
        expected_result_ids=["dummy992", "dummy993"],  # NEW SOUTH WALES, AUSTRALIA
        description="search for new south wales should return new south wales and australia",
    ),
    PrecisionTestCase[Label](
        category="place name + other terms",
        search_terms="Philippines policies in climate changes",
        expected_result_ids=[
            "dummy994",  # PHILIPPINES
            "dummy995",  # POLICIES
            "dummy996",  # CLIMATE
        ],
        description="search for philippines policies in climate changes should return relevant labels first",
    ),
    RecallTestCase[Label](
        category="place name + other terms",
        search_terms="brazil nature based solutions",
        expected_result_ids=["dummy922"],  # BRAZIL
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
        expected_result_ids=["dummy997", "dummy996"],  # LAW, CLIMATE
        k=3,
        description="search for law relating to climate change should return laws or climate labels",
    ),
    PrecisionTestCase[Label](
        category="document name",
        search_terms="national climate plan",
        expected_result_ids=[
            "dummy998",
            "dummy996",
            "dummy999",
        ],  # NATIONAL, CLIMATE, PLAN
        description="search for national climate plan should return relevant labels first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="nz",
        expected_result_ids=[
            "wpx36e4m",  # net-zero target
            "dummy939",  # NEW ZEALAND
        ],
        description="search for nz should return 'new zealand' and 'net zero target' first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="totalenergies",
        expected_result_ids=["dummy933"],  # TOTAL ENERGIES
        description="search for totalenergies should return total energies label first",
    ),
    PrecisionTestCase[Label](
        category="entity name",
        search_terms="european court of human rights",
        expected_result_ids=["dummy932"],  # ECHR
        description="search for european court of human rights should return matching label first",
    ),
    PrecisionTestCase[Label](
        category="question",
        search_terms="How many targets does Canada currently have relating to climate change?",
        expected_result_ids=[
            "sk4kv7u3",  # target
            "dummy933",  # CANADA
            "dummy996",  # CLIMATE
        ],
        description="search about canada targets should return relevant labels first",
    ),
    PrecisionTestCase[Label](
        category="question",
        search_terms="what is the croatias climate strategy",
        expected_result_ids=[
            "wf4tcvtp",  # strategy setting and planning
            "dummy996",  # CLIMATE
            "dummy934",  # POLICY
            "dummy935",  # STRATEGY
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
            "dummy936",  # JAPAN
            "dummy937",  # USA
            "dummy938",  # SWEDEN
            "dummy939",  # CHINA
        ],
        description="search for multiple countries should return labels for those countries first",
    ),
    PrecisionTestCase[Label](
        category="logic",
        search_terms="indigenous people + colombia + laws",
        expected_result_ids=[
            "ptfmpyqe",  # indigenous people
            "6cn2vjae",  # impacted group
            "dummy929",  # COLOMBIA
            "dummy923",  # LAWS
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


@flow(
    name="relevance_tests_labels",
    task_runner=ThreadPoolTaskRunner(max_workers=3),  # type: ignore[arg-type]
)
def relevance_tests_labels():
    """Run relevance tests for labels"""

    engines = [
        VespaLabelSearchEngine(),
    ]

    run_relevance_tests_parallel(
        engines=engines,
        test_cases=test_cases,
        primitive_type=Label,
        output_subdir="labels",
    )


if __name__ == "__main__":
    relevance_tests_labels()
