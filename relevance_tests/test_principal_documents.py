import re

from prefect.task_runners import ThreadPoolTaskRunner

from api.routers import settings
from prefect import flow
from relevance_tests import run_relevance_tests_parallel
from search.data_in_models import Document
from search.engines.dev_vespa import DevVespaPrincipalDocumentSearchEngine
from search.testcase import (
    FieldCharacteristicsTestCase,
    PrecisionTestCase,
    SearchComparisonTestCase,
    all_words_in_string,
)

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
        expected_result_ids=[
            "CCLW.family.11041.0",
        ],
        description="Searching for a document title should return the correct document, where the title has brackets.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="obligation to provide renewable fuels 2005",
        expected_result_ids=[
            # Act (2005:1248) on the obligation to provide renewable fuels
            "CCLW.family.11173.0",
            # Act on the obligation to provide renewable fuels (2005:1248)
            "CCLW.family.i00006852.n0000",
        ],
        description="Searching for a document title where the words are in a different order.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="National Climate Change Strategy 2021-2026",
        expected_result_ids=[
            "CCLW.family.1704.0",
        ],
        description="Searching for the document title should return the correct document.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="fca rules of tcfd",
        expected_result_ids=[
            "CCLW.family.9956.0",
        ],
        description="Acronyms in document titles",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="power up britain",
        expected_result_ids=[
            "CCLW.family.11174.2",
        ],
        description="Stemmed words in document titles",
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="UK Climate Change Act",
        expected_result_ids=[
            "CCLW.family.1755.0",  # "Climate Change Act 2008" from "United Kingdom"
        ],
        description="Searching for title + geography should return the correct document if geography is not in the document title (Climate Change Act 2008)",
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="climate change law uk",
        expected_result_ids=[
            "CCLW.family.1755.0",  # "Climate Change Act 2008" from "United Kingdom"
        ],
        description="Searching for title + geography should return the correct document if geography is not in the document title (Climate Change Act 2008)",
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="energy policy act us",
        expected_result_ids=[
            "CCLW.family.1776.0",
        ],
        description="Searching for title + geography should return the correct document if geography is not in the document title (Energy Policy Act 2005 (Energy Bill))",
    ),
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="adaptation strategy",
        characteristics_test=lambda document: all_words_in_string(
            ["adaptation", "strategy"], document.title
        ),
        description="Search for 'Adaptation Strategy' should contain at least 5 adaptation strategies first.",
        k=5,
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
        characteristics_test=lambda document: "national communication"
        in document.title.lower(),
        description="Search for 'National Communication' should contain at least 5 national communications first.",
        k=5,
    ),
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="national communication",
        characteristics_test=lambda document: "national communication"
        in document.title.lower(),
        description="Search for 'National Communication' should contain at least 20 national communications first.",
        k=20,
    ),
    PrecisionTestCase[Document](
        category="document name",
        search_terms="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
        expected_result_ids=[
            "CCLW.family.11091.1",
        ],
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
        expected_result_ids=[
            "UNFCCC.family.i00002621.n0000",  # Argentina's Long-Term Low-Emission Development Strategy. LT-LEDS1
        ],
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
        # There are only 2 principal docs with mileudefensie in the title
        k=2,
    ),
    # TODO: not sure what the correct case is for this
    # PrecisionTestCase[Document](
    #     category="entity name",
    #     search_terms="Municipalities of Puerto Rico v. Exxon Mobil Corp.",
    #     expected_result_ids=[],
    #     description="Searching for 'Municipalities of Puerto Rico v. Exxon Mobil Corp.' should return case Commonwealth of Puerto Rico v. Exxon Mobil Corp.",
    # ),
    FieldCharacteristicsTestCase[Document](
        category="question",
        search_terms="what is the croatias climate strategy",
        characteristics_test=lambda document: all_words_in_string(
            ["climate", "strategy"], document.title
        )
        and any(
            (relationship.value.value == "Croatia" and relationship.type == "geography")
            for relationship in document.labels
        ),
        description="Search for 'what is the croatias climate strategy' should return documents with titles indicating they're climate strategies with geography 'Croatia'",
        k=5,
    ),
    # TODO (all docket number tests): making these FieldCharacteristicsTestCases would mean they're much easier parametrisable
    # for a handful of docket numbers, expanding our sense of where this test works and doesn't. That relies on us using a
    # non-Huggingface data source which has docket number in document metadata.
    PrecisionTestCase[Document](
        category="docket number",
        search_terms="1:25-cv-02214",
        expected_result_ids=["Sabin.family.130975.0"],
        description="Searching for docket number of US case should return all the documents from the case first.",
    ),
    PrecisionTestCase[Document](
        category="docket number",
        search_terms="13-1820",
        expected_result_ids=["Sabin.family.1221.0"],
        # expected_result_ids=["Sabin.document.1221.3369"],
        # testing for returning the correct family until search result design is finalised.  Only families have docket numbers in current metadata
        description="Searching for docket number of US case should return all the documents from the case first.",
    ),
    PrecisionTestCase[Document](
        category="docket number",
        search_terms="24-3397",
        expected_result_ids=["Sabin.family.69198.0"],
        # expected_result_ids=["Sabin.document.69198.69199"],
        # testing for returning the correct family until search result design is finalised.  Only families have docket numbers in current metadata
        description="Searching for docket number of US case should return all the documents from the case first.",
    ),
    PrecisionTestCase[Document](
        category="project id number",
        search_terms="5567",
        expected_result_ids=["GEF.family.5567.0"],
        # expected_result_ids=[""],
        # testing for returning the correct family until search result design is finalised.  Only families have project ids in current metadata
        description="Searching for the project id of an MCF project should return the correct project.",
    ),
    PrecisionTestCase[Document](
        category="project id number",
        search_terms="27920",
        expected_result_ids=["GCF.family.FP278.27920"],
        # expected_result_ids=[""],
        # testing for returning the correct family until search result design is finalised.  Only families have project ids in current metadata
        description="Searching for the project id of an MCF project should return the correct project.",
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name + acronym",
        search_terms="erp",
        characteristics_test=lambda document: bool(
            re.search(r"\bemissions?\b", document.title, re.IGNORECASE)
        )
        and "reduction" in document.title.lower()
        and "plan" in document.title.lower(),
        description="Search for 'erp' should return documents with 'emission(s) reduction plan' in the title",
        k=10,
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name + acronym",
        search_terms="necp",
        characteristics_test=lambda document: all_words_in_string(
            ["national", "energy", "climate", "plan"], document.title
        ),
        description="Search for 'necp' should return documents with the NECP word set in the title",
        k=10,
    ),
    # TODO: use relevant labels if they exist, e.g., document type = "climate action plan"
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="climate action plan",
        characteristics_test=lambda document: all_words_in_string(
            ["climate", "action", "plan"], document.title
        ),
        description="Search for 'climate action plan' should return documents with that phrase in the title",
        k=10,
    ),
    SearchComparisonTestCase[Document](
        category="spelling",
        search_terms="phaseout",
        search_terms_to_compare="phase out",
        description="Searches for 'phaseout' and 'phase out' should return the same top few documents, like the Japanese policy on phaseout of inefficient coal and Chilean phaseout document",
        k=5,
        minimum_overlap=1.0,
        strict_order=False,
    ),
    PrecisionTestCase[Document](
        category="document name+acronym",
        search_terms="sfdr",
        expected_result_ids=[
            "CCLW.family.9520.0",
        ],
        description="searching for 'sfdr' should return the EU Sustainable Finance Disclosure Regulation",
    ),
    PrecisionTestCase[Document](
        category="document name+acronym",
        search_terms="ira",
        expected_result_ids=[
            "CCLW.family.10699.0",
        ],
        description="searching for 'ira' should return the Inflation Reduction Act",
    ),
    PrecisionTestCase[Document](
        category="document name",
        search_terms="uganda climate change act",
        expected_result_ids=[
            "CCLW.family.10180.0",  # National Climate Change Act 2021
            "CPR.family.i00002330.n0000",  # Uganda National Climate Change Act 2021
        ],
        description="Searching for a title plus geography should return the correct document even when the geography is not in the title",
    ),
    # TODO: this search returns a lot of uganda climate change laws, but not the climate change act specified as result number 1
    # The results returned are: Uganda: National climate change policy; Uganda National Climate Change Act 2021; Uganda National Climate Change Communication Strategy (UNCCCS) 2017...
    PrecisionTestCase[Document](
        category="document name",
        search_terms="climate change law uganda",
        expected_result_ids=[
            "CCLW.family.10180.0",
        ],
        description="Searching for a title plus geography should return the correct document even when the geography is not in the title",
    ),
    PrecisionTestCase[Document](
        category="document name+acronym",
        search_terms="ev mandate",
        expected_result_ids=[
            "CCLW.family.i00001515.n0000",  # there is a duplicate family with year 0 in the metadata (CCLW.family.i00000771.n0000, the-vehicle-emissions-trading-schemes-order-2023_260e)
            "CPR.family.i00000386.n0000",
        ],
        description="searching for 'ev mandate' as the commonly understood topic of the legislation when not obvious from the title but stated in the summary should return the UK's Vehicle Emissions Trading Schemes Order 2023 and Canada's Electric Vehicle Availability Standard in the top results",
    ),
    PrecisionTestCase[Document](
        category="document name+acronym",
        search_terms="zev mandate",
        expected_result_ids=[
            "CCLW.family.i00001515.n0000",  # there is a duplicate family with year 0 in the metadata (CCLW.family.i00000771.n0000, the-vehicle-emissions-trading-schemes-order-2023_260e)
            "CPR.family.i00000386.n0000",
        ],
        description="searching for 'zev mandate' as the commonly understood topic of the legislation when not obvious from the title but stated in the summary should return the UK's Vechicle Emissions Trading Schemes Order 2023 and Canada's Electric Vehicle Availability Standard in the top results",
    ),
    PrecisionTestCase[Document](
        category="document name",
        search_terms="safeguard mechanism",
        expected_result_ids=[
            "CCLW.family.i00006699.n0000",  # "National Greenhouse and Energy Reporting (Safeguard Mechanism) Rule 2015, Australia"
            "CCLW.family.11176.0",  # 'Safeguard Mechanism (Crediting) Amendment Act 2023, Australia
            # TODO: add more documents if they exist
        ],
        description="searching for 'safeguard mechanism' should return documents about the Australian policy instrument whose short name is 'safeguard mechanism'",
    ),
    FieldCharacteristicsTestCase[Document](
        category="document type",
        search_terms="taxonomy",
        characteristics_test=lambda document: "taxonomy" in document.title.lower(),
        description="Search for 'taxonomy' return green taxonomies with the term in the title",
        k=5,
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="governance regulation",
        expected_result_ids=[
            "CCLW.family.9492.0",  # "Regulation 2018/1999 on the Governance of the Energy Union and Climate Action" (regulation-2018-1999-on-the-governance-of-the-energy-union-and-climate-action_26fa) and all documents on the family page
        ],
        description="searching for 'governance regulation' should the EU Governance Regulation, even when the term is not in the title",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="five year plan",
        expected_result_ids=[
            "CCLW.family.10087.0",  # The most recent of China's five-year plans (15th).  Further guidance needed on which of the many other documents should be included in this test
        ],
        description="searching for 'five year plan' should return China's five-year plans first",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="United Kingdom Nationally Determined Contribution. NDC3.0",
        expected_result_ids=[
            "UNFCCC.family.i00000492.n0000",  # "United Kingdom  Nationally Determined Contribution. NDC3.0" (united-kingdom-nationally-determined-contribution-ndc3-0_aad3)
        ],
        description="searching for 'United Kingdom Nationally Determined Contribution. NDC3.0' should return that family as the top result",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="Regulation (EU) 2024/795",
        expected_result_ids=[
            "CCLW.family.10795.0",  # "Regulation (EU) 2021/1056 establishing the Just Transition Fund, amended by Regulation (EU) 2024/795 and Regulation (EU) 2025/1914"
        ],
        description="searching for the title of an amending regulation should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="Decision Introducing the Natural Resources and Environment Action Program for Implementation of the National Green Growth Strategy",
        expected_result_ids=[
            "CCLW.family.1793.0",  # "National Green Growth Strategy"
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="Decision Approving the Cooperation Program for Climate Change and Green Growth in the 2016-2020 Period",
        expected_result_ids=[
            "CCLW.family.1793.0",  # "National Green Growth Strategy"
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="Decree No. 58/2025/ND-CP on the development of renewable energy and new energy electricity",
        expected_result_ids=[
            "CCLW.family.i00008825.n0000",
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="Long-term Energy Supply and Demand Outlook",
        expected_result_ids=[
            "CCLW.family.8646.0",  # 5th Strategic Energy Plan
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="The Plan to Deliver Net Zero the Australian Way",
        expected_result_ids=[
            "CCLW.family.10328.0",
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="13th Five-Year Plan for National Economic and Social Development",
        expected_result_ids=[
            "CCLW.family.10087.0",
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
    PrecisionTestCase[Document](
        category="non principal document by title",
        search_terms="Carbon Sinks Strategy",
        expected_result_ids=[
            "CCLW.family.i00000498.n0000",  # "Carbon Sinks Strategy (draft)"
        ],
        description="searching for a child document title should return its parent family in principal search",
    ),
]


@flow(
    name="relevance_tests_principal_documents",
    task_runner=ThreadPoolTaskRunner(max_workers=3),  # type: ignore[arg-type]
)
def relevance_tests_principal_documents():
    """Run relevance tests for documents"""

    engines = [
        DevVespaPrincipalDocumentSearchEngine(settings=settings, debug=True),
    ]

    # Principals aren't a primitive, but we use the primitive name to determine where
    # to store the results of the relevance tests. This is a hacky way to achieve this
    # without having to maintain a new `Principal` type which might cause confusion
    # if used elsewhere.
    Principal = Document
    Principal.__name__ = "Principal"

    run_relevance_tests_parallel(
        engines=engines,
        test_cases=test_cases,
        primitive_type=Principal,
        output_subdir="principal_documents",
    )


if __name__ == "__main__":
    relevance_tests_principal_documents()
