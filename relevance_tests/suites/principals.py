from pydantic_evals import Dataset

from api.routers import settings
from relevance_tests.evaluators.overlap import Overlap
from relevance_tests.evaluators.precision import Precision
from relevance_tests.evaluators.recall import Recall
from relevance_tests.suites.documents import (
    DocumentMatches,
    DocumentQuery,
    QueryPair,
    SearchPair,
)
from search.data_in_models import Document
from search.engines import ListResponse, OrderBy, Pagination
from search.engines.dev_vespa import DevVespaPrincipalDocumentSearchEngine

# 0.7 because that is what the frontend sends with every text search (FUS-421)
engine = DevVespaPrincipalDocumentSearchEngine(settings=settings, msm=0.7)


dataset = Dataset[DocumentQuery, ListResponse[Document], dict[str, str]](
    name="principals",
    cases=[],
)

dataset.add_case(
    name="Directive (EU) 2022/2464 amending Regulation (EU) No 537/2014",
    inputs=DocumentQuery(
        query="Directive (EU) 2022/2464 amending Regulation (EU) No 537/2014 and others, as regards corporate sustainability reporting (Corporate Sustainability Reporting Directive or CSRD)",
    ),
    metadata={"category": "punctuation"},
    evaluators=[Precision(expected=["CCLW.family.11041.0"], k=1)],
)

dataset.add_case(
    name="obligation to provide renewable fuels 2005",
    inputs=DocumentQuery(query="obligation to provide renewable fuels 2005"),
    metadata={"category": "specific document"},
    evaluators=[
        Precision(
            expected=[
                # Act (2005:1248) on the obligation to provide renewable fuels
                "CCLW.family.11173.0",
                # Act on the obligation to provide renewable fuels (2005:1248)
                "CCLW.family.i00006852.n0000",
            ],
            k=2,
        ),
    ],
)

dataset.add_case(
    name="National Climate Change Strategy 2021-2026",
    inputs=DocumentQuery(query="National Climate Change Strategy 2021-2026"),
    metadata={"category": "specific document"},
    evaluators=[Precision(expected=["CCLW.family.1704.0"], k=1)],
)

dataset.add_case(
    name="fca rules of tcfd",
    inputs=DocumentQuery(query="fca rules of tcfd"),
    metadata={"category": "specific document"},
    evaluators=[Precision(expected=["CCLW.family.9956.0"], k=1)],
)

dataset.add_case(
    name="power up britain",
    inputs=DocumentQuery(query="power up britain"),
    metadata={"category": "specific document"},
    evaluators=[Precision(expected=["CCLW.family.11174.2"], k=1)],
)

for query in ["UK Climate Change Act", "climate change law uk"]:
    dataset.add_case(
        name=query,
        inputs=DocumentQuery(query=query),
        metadata={"category": "document name + geography"},
        evaluators=[
            Precision(
                expected=[
                    # "Climate Change Act 2008" from "United Kingdom"
                    "CCLW.family.1755.0",
                ],
                k=1,
            ),
        ],
    )

dataset.add_case(
    name="energy policy act us",
    inputs=DocumentQuery(query="energy policy act us"),
    metadata={"category": "document name + geography"},
    evaluators=[Precision(expected=["CCLW.family.1776.0"], k=1)],
)

dataset.add_case(
    name="adaptation strategy",
    inputs=DocumentQuery(query="adaptation strategy"),
    metadata={"category": "document type"},
    evaluators=[
        DocumentMatches(pattern=r"(?i)^(?=.*\badaptation\b)(?=.*\bstrategy\b)", k=5),
        DocumentMatches(pattern=r"(?i)^(?=.*\badaptation\b)(?=.*\bstrategy\b)", k=20),
    ],
)

dataset.add_case(
    name="national communication",
    inputs=DocumentQuery(query="national communication"),
    metadata={"category": "document type"},
    evaluators=[
        DocumentMatches(pattern=r"(?i)^.*national communication", k=5),
        DocumentMatches(pattern=r"(?i)^.*national communication", k=20),
    ],
)

dataset.add_case(
    name="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021",
    inputs=DocumentQuery(
        query="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
    ),
    metadata={"category": "document name"},
    evaluators=[Precision(expected=["CCLW.family.11091.1"], k=1)],
)

dataset.add_case(
    name="national climate plan",
    inputs=DocumentQuery(query="national climate plan"),
    metadata={"category": "document type"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?i)^(?=.*\bnational\b)(?=.*\bclimate\b)(?=.*\bplan\b)",
            k=10,
        ),
    ],
)

dataset.add_case(
    name="argentina LT-LEDS",
    inputs=DocumentQuery(query="argentina LT-LEDS"),
    metadata={"category": "document name"},
    evaluators=[
        Precision(
            expected=[
                # Argentina's Long-Term Low-Emission Development Strategy. LT-LEDS1
                "UNFCCC.family.i00002621.n0000",
            ],
            k=1,
        ),
    ],
)

dataset.add_case(
    name="nz",
    inputs=DocumentQuery(query="nz"),
    metadata={"category": "entity name"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?i)^.*(\bnz\b|\bnew\W+zealand\b|\bnet\W+zero\b)",
            k=10,
        ),
    ],
)

dataset.add_case(
    name="juliana",
    inputs=DocumentQuery(query="juliana"),
    metadata={"category": "entity name"},
    evaluators=[DocumentMatches(pattern=r"(?i)^.*juliana", k=5)],
)

dataset.add_case(
    name="milieudefensie",
    inputs=DocumentQuery(query="milieudefensie"),
    metadata={"category": "entity name"},
    # There are only 2 principal docs with milieudefensie in the title
    evaluators=[DocumentMatches(pattern=r"(?i)^.*milieudefensie", k=2)],
)

dataset.add_case(
    name="what is the croatias climate strategy",
    inputs=DocumentQuery(query="what is the croatias climate strategy"),
    metadata={"category": "question"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?im)\A(?=.*\bclimate\b)(?=.*\b(strategy|plan|programme)\b)(?=[\s\S]*^geography::Croatia$)",
            k=5,
        ),
    ],
)

# Only families have docket numbers and project ids in current metadata, so these
# expect the family until search result design is finalised
dataset.add_case(
    name="1:25-cv-02214",
    inputs=DocumentQuery(query="1:25-cv-02214"),
    metadata={"category": "docket number"},
    evaluators=[Precision(expected=["Sabin.family.130975.0"], k=1)],
)

dataset.add_case(
    name="13-1820",
    inputs=DocumentQuery(query="13-1820"),
    metadata={"category": "docket number"},
    evaluators=[Precision(expected=["Sabin.family.1221.0"], k=1)],
)

dataset.add_case(
    name="24-3397",
    inputs=DocumentQuery(query="24-3397"),
    metadata={"category": "docket number"},
    evaluators=[Precision(expected=["Sabin.family.69198.0"], k=1)],
)

dataset.add_case(
    name="5567",
    inputs=DocumentQuery(query="5567"),
    metadata={"category": "project id number"},
    evaluators=[Precision(expected=["GEF.family.5567.0"], k=1)],
)

dataset.add_case(
    name="27920",
    inputs=DocumentQuery(query="27920"),
    metadata={"category": "project id number"},
    evaluators=[Precision(expected=["GCF.family.FP278.27920"], k=1)],
)

dataset.add_case(
    name="erp",
    inputs=DocumentQuery(query="erp"),
    metadata={"category": "entity name + acronym"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?i)^(?=.*\bemissions?\b)(?=.*reduction)(?=.*plan)",
            k=10,
            all_or_any="any",
        ),
    ],
)

dataset.add_case(
    name="necp",
    inputs=DocumentQuery(query="necp"),
    metadata={"category": "entity name + acronym"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?i)^(?=.*\bnational\b)(?=.*\benergy\b)(?=.*\bclimate\b)(?=.*\bplan\b)",
            k=10,
            all_or_any="any",
        ),
    ],
)

dataset.add_case(
    name="climate action plan",
    inputs=DocumentQuery(query="climate action plan"),
    metadata={"category": "document type"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?i)^(?=.*\bclimate\b)(?=.*\baction\b)(?=.*\bplan\b)",
            k=10,
        ),
    ],
)

dataset.add_case(
    name="sfdr",
    inputs=DocumentQuery(query="sfdr"),
    metadata={"category": "document name+acronym"},
    evaluators=[Precision(expected=["CCLW.family.9520.0"], k=1)],
)

dataset.add_case(
    name="ira",
    inputs=DocumentQuery(query="ira"),
    metadata={"category": "document name+acronym"},
    evaluators=[
        Precision(
            expected=[
                # Inflation Reduction Act
                "CCLW.family.10699.0",
                # United States — Certain Tax Credits Under the Inflation Reduction Act
                "Sabin.family.109771.0",
            ],
            k=2,
        ),
    ],
)

for query in ["uganda climate change act", "climate change law uganda"]:
    dataset.add_case(
        name=query,
        inputs=DocumentQuery(query=query),
        metadata={"category": "document name"},
        evaluators=[
            Precision(
                expected=[
                    # National Climate Change Act 2021
                    "CCLW.family.10180.0",
                    # Uganda National Climate Change Act 2021
                    "CPR.family.i00002330.n0000",
                ],
                k=2,
            ),
        ],
    )

for query in ["ev mandate", "zev mandate"]:
    dataset.add_case(
        name=query,
        inputs=DocumentQuery(query=query),
        metadata={"category": "document name+acronym"},
        evaluators=[
            Precision(
                expected=[
                    # The UK's Vehicle Emissions Trading Schemes Order 2023. There is
                    # a duplicate family with year 0 (CCLW.family.i00000771.n0000)
                    "CCLW.family.i00001515.n0000",
                    # Canada's Electric Vehicle Availability Standard
                    "CPR.family.i00000386.n0000",
                ],
                k=2,
            ),
        ],
    )

dataset.add_case(
    name="safeguard mechanism",
    inputs=DocumentQuery(query="safeguard mechanism"),
    metadata={"category": "document name"},
    evaluators=[
        Precision(
            expected=[
                # National Greenhouse and Energy Reporting (Safeguard Mechanism) Rule 2015
                "CCLW.family.i00006699.n0000",
                # Safeguard Mechanism (Crediting) Amendment Act 2023
                "CCLW.family.11176.0",
            ],
            k=2,
        ),
    ],
)

dataset.add_case(
    name="taxonomy",
    inputs=DocumentQuery(query="taxonomy"),
    metadata={"category": "document type"},
    evaluators=[DocumentMatches(pattern=r"(?i)^.*taxonomy", k=5)],
)

dataset.add_case(
    name="governance regulation",
    inputs=DocumentQuery(query="governance regulation"),
    metadata={"category": "specific document"},
    evaluators=[
        Precision(
            expected=[
                # Regulation 2018/1999 on the Governance of the Energy Union and
                # Climate Action
                "CCLW.family.9492.0",
            ],
            k=1,
        ),
    ],
)

dataset.add_case(
    name="five year plan",
    inputs=DocumentQuery(query="five year plan"),
    metadata={"category": "specific document"},
    evaluators=[
        Precision(
            expected=[
                # China's most recent (15th) five-year plan
                "CCLW.family.10087.0",
            ],
            k=1,
        ),
    ],
)

dataset.add_case(
    name="United Kingdom Nationally Determined Contribution. NDC3.0",
    inputs=DocumentQuery(
        query="United Kingdom Nationally Determined Contribution. NDC3.0",
    ),
    metadata={"category": "specific document"},
    evaluators=[Precision(expected=["UNFCCC.family.i00000492.n0000"], k=1)],
)

dataset.add_case(
    name="Regulation (EU) 2024/795",
    inputs=DocumentQuery(query="Regulation (EU) 2024/795"),
    metadata={"category": "non principal document by title"},
    evaluators=[
        Precision(
            expected=[
                # Regulation (EU) 2021/1056 establishing the Just Transition Fund,
                # amended by Regulation (EU) 2024/795 and Regulation (EU) 2025/1914
                "CCLW.family.10795.0",
            ],
            k=1,
        ),
    ],
)

for query in [
    "Decision Introducing the Natural Resources and Environment Action Program for Implementation of the National Green Growth Strategy",
    "Decision Approving the Cooperation Program for Climate Change and Green Growth in the 2016-2020 Period",
]:
    dataset.add_case(
        name=query,
        inputs=DocumentQuery(query=query),
        metadata={"category": "non principal document by title"},
        evaluators=[
            Precision(
                expected=[
                    # National Green Growth Strategy
                    "CCLW.family.1793.0",
                ],
                k=1,
            ),
        ],
    )

dataset.add_case(
    name="Decree No. 58/2025/ND-CP",
    inputs=DocumentQuery(
        query="Decree No. 58/2025/ND-CP on the development of renewable energy and new energy electricity",
    ),
    metadata={"category": "non principal document by title"},
    evaluators=[Precision(expected=["CCLW.family.i00008825.n0000"], k=1)],
)

dataset.add_case(
    name="Long-term Energy Supply and Demand Outlook",
    inputs=DocumentQuery(query="Long-term Energy Supply and Demand Outlook"),
    metadata={"category": "non principal document by title"},
    evaluators=[
        Precision(
            expected=[
                # 5th Strategic Energy Plan
                "CCLW.family.8646.0",
            ],
            k=1,
        ),
    ],
)

dataset.add_case(
    name="The Plan to Deliver Net Zero the Australian Way",
    inputs=DocumentQuery(query="The Plan to Deliver Net Zero the Australian Way"),
    metadata={"category": "non principal document by title"},
    evaluators=[Precision(expected=["CCLW.family.10328.0"], k=1)],
)

dataset.add_case(
    name="13th Five-Year Plan for National Economic and Social Development",
    inputs=DocumentQuery(
        query="13th Five-Year Plan for National Economic and Social Development",
    ),
    metadata={"category": "non principal document by title"},
    evaluators=[Precision(expected=["CCLW.family.10087.0"], k=1)],
)

dataset.add_case(
    name="Carbon Sinks Strategy",
    inputs=DocumentQuery(query="Carbon Sinks Strategy"),
    metadata={"category": "non principal document by title"},
    evaluators=[
        Precision(
            expected=[
                # Carbon Sinks Strategy (draft)
                "CCLW.family.i00000498.n0000",
            ],
            k=1,
        ),
    ],
)

# FUS-326
dataset.add_case(
    name="colombia BTR",
    inputs=DocumentQuery(query="colombia BTR"),
    metadata={"category": "document name+acronym"},
    evaluators=[
        Precision(
            expected=[
                # "Colombia Biennial Transparency Report. BTR1" - the only Colombian
                # principal document whose title carries the BTR acronym
                "UNFCCC.family.i00000892.n0000",
            ],
            k=1,
        ),
    ],
)

dataset.add_case(
    name="united kingdom NDC",
    inputs=DocumentQuery(query="united kingdom NDC"),
    metadata={"category": "document name+acronym"},
    evaluators=[
        Precision(
            expected=[
                # United Kingdom Nationally Determined Contribution. NDC3.0
                "UNFCCC.family.i00000492.n0000",
                # ... NDC1 (Updated Submission, 2020)
                "UNFCCC.family.1521.0",
                # ... NDC1 (Updated to 2030)
                "UNFCCC.family.1522.0",
            ],
            k=3,
        ),
    ],
)

dataset.add_case(
    name="mangrove regulation",
    inputs=DocumentQuery(query="mangrove regulation"),
    metadata={"category": "rare term + common term"},
    evaluators=[DocumentMatches(pattern=r"(?i)^.*mangrove", k=5)],
)

dataset.add_case(
    name="electric arc furnace",
    inputs=DocumentQuery(query="electric arc furnace"),
    metadata={"category": "rare term + common term"},
    evaluators=[
        Precision(
            expected=[
                # "Energy Resources Regulations (Energy labeling of electric heating
                # furnaces)" - the only principal document matching two of the three
                # terms. Previously rank 17, behind "Electricity Act" documents
                # matching only "electric"
                "CCLW.family.8267.0",
            ],
            k=1,
        ),
    ],
)

dataset.add_case(
    name="air pollution",
    inputs=DocumentQuery(query="air pollution", corpus="ccc"),
    metadata={"category": "topic name"},
    evaluators=[
        Recall(
            expected=[
                # Ohio v. EPA
                "Sabin.family.16851.0",
            ],
            k=20,
        ),
    ],
)

dataset.add_case(
    name="loss & damage finance",
    inputs=DocumentQuery(query="loss & damage finance"),
    metadata={"category": "topic name"},
    evaluators=[Recall(expected=["UNFCCC.family.i00004847.n0000"], k=20)],
)


def run_search(input: DocumentQuery) -> ListResponse[Document]:
    return engine.search(
        order_by=[OrderBy(field="relevance", direction="desc")],
        pagination=Pagination(page_token=1, page_size=20),
        query=input.query,
        filters=input.filters(),
    )


comparisons = Dataset[QueryPair, SearchPair, dict[str, str]](
    name="principal_comparisons",
    cases=[],
)

comparisons.add_case(
    name="obligation to provide renewable fuel(s) 2005",
    inputs=QueryPair(
        query="obligation to provide renewable fuels 2005",
        other="obligation to provide renewable fuel 2005",
    ),
    metadata={"category": "duplicates"},
    evaluators=[Overlap(k=5)],
)

comparisons.add_case(
    name="phaseout",
    inputs=QueryPair(query="phaseout", other="phase out"),
    metadata={"category": "spelling"},
    evaluators=[Overlap(k=5)],
)


def run_pair(input: QueryPair) -> SearchPair:
    return SearchPair(
        first=engine.search(
            order_by=[OrderBy(field="relevance", direction="desc")],
            pagination=Pagination(page_token=1, page_size=20),
            query=input.query,
        ),
        second=engine.search(
            order_by=[OrderBy(field="relevance", direction="desc")],
            pagination=Pagination(page_token=1, page_size=20),
            query=input.other,
        ),
    )
