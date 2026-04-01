from prefect.task_runners import ThreadPoolTaskRunner

from api.dev import settings
from prefect import flow
from relevance_tests import run_relevance_tests_parallel
from search.data_in_models import Document
from search.engines.dev_vespa import DevVespaDocumentSearchEngine
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
            "CCLW.legislative.11041.6337",
        ],
        description="Searching for a document title should return the correct document, where the title has brackets.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="obligation to provide renewable fuels 2005",
        expected_result_ids=[
            # Act (2005:1248) on the obligation to provide renewable fuels
            "CCLW.family.11173.0",
            "CCLW.legislative.11173.6585",
            # Act on the obligation to provide renewable fuels (2005:1248)
            "CCLW.family.i00006852.n0000",
            "CCLW.document.i00006853.n0000",
        ],
        description="Searching for a document title where the words are in a different order.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="National Climate Change Strategy 2021-2026",
        expected_result_ids=[
            "CCLW.family.1704.0",
            "CCLW.executive.1704.1595",
        ],
        description="Searching for the document title should return the correct document.",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="fca rules of tcfd",
        expected_result_ids=["CCLW.family.9956.0", "CCLW.executive.9956.4413"],
        description="Acronyms in document titles",
    ),
    PrecisionTestCase[Document](
        category="specific document",
        search_terms="power up britain",
        expected_result_ids=[
            "CCLW.executive.11174.6586",
            "CCLW.executive.11174.6588",
            "CCLW.family.11174.2",
            "CCLW.collection.11174.0",
        ],
        description="Stemmed words in document titles",
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="UK Climate Change Act",
        expected_result_ids=[
            # "UK Climate Change Act" with no geography
            "CCLW.collection.1755.0",
            # "Climate Change Act 2008" from "United Kingdom"
            "CCLW.family.1755.0",
            "CCLW.legislative.1755.2260",
            "CCLW.legislative.1755.rtl_71",
        ],
        description="Searching for title + geography should return the correct document if geography is not in the document title (Climate Change Act 2008)",
    ),
    SearchComparisonTestCase[Document](
        category="equivalent terms",
        search_terms="uk climate change act",
        search_terms_to_compare="climate change law uk",
        description="Searches for equivalent terms should return the same top few documents (namely the UK Climate Change Act 2008)",
        k=5,
        minimum_overlap=1.0,
        strict_order=False,
    ),
    PrecisionTestCase[Document](
        category="document name + geography",
        search_terms="energy policy act us",
        expected_result_ids=[
            "CCLW.family.1776.0",
            "CCLW.legislative.1776.2144",
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
            "CCLW.legislative.11091.6395",
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
            # Argentina's Long-Term Strategies (LT-LEDS)
            "UNFCCC.collection.i00006905.n0000",
            # Argentina's Long-Term Low-Emission Development Strategy. LT-LEDS1
            "UNFCCC.family.i00002621.n0000",
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
        k=5,
    ),
    PrecisionTestCase[Document](
        category="entity name",
        search_terms="Municipalities of Puerto Rico v. Exxon Mobil Corp.",
        expected_result_ids=[],
        description="Searching for 'Municipalities of Puerto Rico v. Exxon Mobil Corp.' should return case Commonwealth of Puerto Rico v. Exxon Mobil Corp.",
    ),
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
        expected_result_ids=[
            "Sabin.document.130975.130977",
            "Sabin.document.130975.130978",
            "Sabin.document.130975.130979",
        ],
        description="Searching for docket number of US case should return all the documents from the case first.",
    ),
    PrecisionTestCase[Document](
        category="docket number",
        search_terms="13-1820",
        expected_result_ids=["Sabin.document.1221.3369"],
        description="Searching for docket number of US case should return all the documents from the case first.",
    ),
    PrecisionTestCase[Document](
        category="docket number",
        search_terms="24-3397",
        expected_result_ids=["Sabin.document.69198.69199"],
        description="Searching for docket number of US case should return all the documents from the case first.",
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name + acronym",
        search_terms="erp",
        characteristics_test=lambda document: any(
            term in document.title.lower() for term in ["emissions reduction plan"]
        ),
        description="Search for 'erp' should return documents with 'emissions reduction plan' in the title",
        k=10,
    ),
    FieldCharacteristicsTestCase[Document](
        category="entity name + acronym",
        search_terms="necp",
        characteristics_test=lambda document: any(
            term in document.title.lower()
            for term in ["national energy and climate plan", "necp"]
        ),
        description="Search for 'necp' should return documents with 'national energy and climate plan' or 'necp' in the title",
        k=10,
    ),
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
            "CCLW.legislative.9520.3859",
            "CCLW.legislative.9520.4620",
            "CCLW.document.i00006386.n0000",
            "CCLW.legislative.9520.6334",
        ],
        description="searching for 'sfdr' should return the EU Sustainable Finance Disclosure Regulation",
    ),
    PrecisionTestCase[Document](
        category="acronym",
        search_terms="ira",
        expected_result_ids=[
            "CCLW.family.10699.0",
            "CCLW.legislative.10699.5931",
            "CCLW.legislative.10699.5933",
        ],
        description="searching for 'ira' should return the Inflation Reduction Act",
    ),
    PrecisionTestCase[Document](
        category="document name",
        search_terms="uganda climate change act",
        expected_result_ids=["CCLW.family.10180.0", "CCLW.legislative.10180.4758"],
        description="Searching for a title plus geography should return the correct document even when the geography is not in the title",
    ),
    SearchComparisonTestCase[Document](
        category="equivalent terms",
        search_terms="uganda climate change act",
        search_terms_to_compare="climate change law uganda",
        description="Searches for equivalent terms should return the same top few documents (namely the Uganda Climate Change Act 2021)",
        k=5,
        minimum_overlap=1.0,
        strict_order=False,
    ),
    PrecisionTestCase[Document](
        category="document name+acronym",
        search_terms="ev mandate",
        expected_result_ids=[
            "CCLW.family.i00001515.n0000",  # there is a duplicate family with year 0 in the metadata (CCLW.family.i00000771.n0000, the-vehicle-emissions-trading-schemes-order-2023_260e)
            # there are also two document pages on CCLW not accessible from the family page:
            "CCLW.document.i00000772.n0000",
            "CCLW.document.i00001516.n0000",
            # Canada--also a document page not accessible from the family page:
            "CPR.family.i00000386.n0000",
            "CPR.document.i00000387.n0000",
        ],
        description="searching for 'ev mandate' as the commonly understood topic of the legislation when not obvious from the title but stated in the summary should return the UK's Vechicle Emissions Trading Schemes Order 2023 and Canada's Electric Vehicle Availability Standard in the top results",
    ),
    SearchComparisonTestCase[Document](
        category="alternate acronyms",
        search_terms="ev mandate",
        search_terms_to_compare="zev mandate",
        description="Searches for 'ev mandate' and 'zev mandate' should return same top few documents relating to electric vehicle and zero emission vehicle mandates",
        k=5,
        minimum_overlap=1.0,
        strict_order=False,
    ),
]


@flow(
    name="relevance_tests_documents",
    task_runner=ThreadPoolTaskRunner(max_workers=3),  # type: ignore[arg-type]
)
def relevance_tests_documents():
    """Run relevance tests for documents"""

    engines = [
        # BM25TitleVespaDocumentSearchEngine(),
        # add debug=True to this engine for a debug summary
        DevVespaDocumentSearchEngine(settings=settings),
    ]

    run_relevance_tests_parallel(
        engines=engines,
        test_cases=test_cases,
        primitive_type=Document,
        output_subdir="documents",
    )


if __name__ == "__main__":
    relevance_tests_documents()
