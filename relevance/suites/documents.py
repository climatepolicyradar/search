from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_evals import Dataset

from api.routers import settings
from relevance.evaluators.matches import Matches
from relevance.evaluators.narrows import Narrows
from relevance.evaluators.overlap import Overlap
from relevance.evaluators.precision import Precision
from relevance.evaluators.recall import Recall
from relevance.evaluators.relative_order import RanksAbove
from search.corpora import Corpus, build_corpus_filter
from search.data_in_models import Document
from search.engines import ListResponse, OrderBy, Pagination
from search.engines.dev_vespa import (
    TOPIC_FILTER_FIELD,
    Condition,
    DevVespaDocumentSearchEngine,
    FieldFilter,
    Filter,
    normalise_topic_id,
)


@dataclass
class DocumentMatches[I](Matches[I, Document]):
    def text(self, result: Document) -> str:
        """The document's title, then one geography::<value> line per geography."""
        return "\n".join(
            [
                result.title,
                *(
                    f"geography::{relationship.value.value}"
                    for relationship in result.labels
                    if relationship.type == "geography"
                ),
            ]
        )


def build_topic_filter(topics: list[str]) -> Filter | None:
    """
    AND the topics together into a single condition, or None if there are none.

    Each topic sits in its own nested group because topics in a group would get collapsed
    by the engine into a single `sameElement(...)`, so match nothing. See
    `_build_filter_yql` in `search/engines/vespa_query/filters.py`.
    """
    if not topics:
        return None
    return Filter(
        op="and",
        filters=[
            Filter(
                op="or",
                filters=[
                    FieldFilter(
                        field=TOPIC_FILTER_FIELD,
                        op="contains",
                        value=normalise_topic_id(topic),
                    )
                ],
            )
            for topic in topics
        ],
    )


class DocumentQuery(BaseModel):
    query: str
    topics: list[str] = []
    corpus: Corpus | None = None

    def filters(self) -> Filter | None:
        """Vespa filter for the query's topics and corpus, or None."""
        conditions: list[Condition | Filter] = []
        if topic_filter := build_topic_filter(self.topics):
            conditions.append(topic_filter)
        if self.corpus is not None:
            conditions.append(build_corpus_filter(self.corpus))
        if not conditions:
            return None
        return Filter(op="and", filters=conditions)


class QueryPair(BaseModel):
    query: str
    other: str


class SearchPair(BaseModel):
    first: ListResponse[Document]
    second: ListResponse[Document]


# 0.7 because that is what the frontend sends with every text search (FUS-421),
engine = DevVespaDocumentSearchEngine(settings=settings, msm=0.7)


dataset = Dataset[DocumentQuery, ListResponse[Document], dict[str, str]](
    name="documents",
    cases=[],
)

dataset.add_case(
    name="Directive (EU) 2022/2464 amending Regulation (EU) No 537/2014",
    inputs=DocumentQuery(
        query="Directive (EU) 2022/2464 amending Regulation (EU) No 537/2014 and others, as regards corporate sustainability reporting (Corporate Sustainability Reporting Directive or CSRD)",
    ),
    metadata={"category": "punctuation"},
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.11041.0",
                "CCLW.legislative.11041.6337",
            ],
            k=2,
        ),
    ],
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
                "CCLW.legislative.11173.6585",
                # Act on the obligation to provide renewable fuels (2005:1248)
                "CCLW.family.i00006852.n0000",
                "CCLW.document.i00006853.n0000",
            ],
            k=4,
        ),
    ],
)

dataset.add_case(
    name="National Climate Change Strategy 2021-2026",
    inputs=DocumentQuery(query="National Climate Change Strategy 2021-2026"),
    metadata={"category": "specific document"},
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.1704.0",
                "CCLW.executive.1704.1595",
            ],
            k=2,
        ),
    ],
)

dataset.add_case(
    name="fca rules of tcfd",
    inputs=DocumentQuery(query="fca rules of tcfd"),
    metadata={"category": "specific document"},
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.9956.0",
                "CCLW.executive.9956.4413",
            ],
            k=2,
        ),
    ],
)

dataset.add_case(
    name="power up britain",
    inputs=DocumentQuery(query="power up britain"),
    metadata={"category": "specific document"},
    evaluators=[
        Precision(
            expected=[
                "CCLW.executive.11174.6586",
                "CCLW.executive.11174.6588",
                "CCLW.family.11174.2",
                "CCLW.collection.11174.0",
            ],
            k=4,
        ),
    ],
)

for query in ["UK Climate Change Act", "climate change law uk"]:
    dataset.add_case(
        name=query,
        inputs=DocumentQuery(query=query),
        metadata={"category": "document name + geography"},
        evaluators=[
            Precision(
                expected=[
                    # "UK Climate Change Act" with no geography
                    "CCLW.collection.1755.0",
                    # "Climate Change Act 2008" from "United Kingdom"
                    "CCLW.family.1755.0",
                    "CCLW.legislative.1755.2260",
                    "CCLW.legislative.1755.rtl_71",
                ],
                k=4,
            ),
        ],
    )

dataset.add_case(
    name="energy policy act us",
    inputs=DocumentQuery(query="energy policy act us"),
    metadata={"category": "document name + geography"},
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.1776.0",
                "CCLW.legislative.1776.2144",
            ],
            k=2,
        ),
    ],
)

# Multi-word geography aliases (FUS-423)
dataset.add_case(
    name="ivory coast",
    inputs=DocumentQuery(query="ivory coast"),
    metadata={"category": "document name + geography"},
    evaluators=[DocumentMatches(pattern=r"(?im)^geography::.*\bivoire\b", k=5)],
)

dataset.add_case(
    name="czech republic",
    inputs=DocumentQuery(query="czech republic"),
    metadata={"category": "document name + geography"},
    evaluators=[DocumentMatches(pattern=r"(?im)^geography::.*\bczechia\b", k=5)],
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
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.11091.1",
                "CCLW.legislative.11091.6395",
            ],
            k=2,
        ),
    ],
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
                # Argentina's Long-Term Strategies (LT-LEDS)
                "UNFCCC.collection.i00006905.n0000",
                # Argentina's Long-Term Low-Emission Development Strategy. LT-LEDS1
                "UNFCCC.family.i00002621.n0000",
            ],
            k=2,
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

for query in ["juliana", "milieudefensie"]:
    dataset.add_case(
        name=query,
        inputs=DocumentQuery(query=query),
        metadata={"category": "entity name"},
        evaluators=[DocumentMatches(pattern=rf"(?i)^.*{query}", k=5)],
    )

dataset.add_case(
    name="what is the croatias climate strategy",
    inputs=DocumentQuery(query="what is the croatias climate strategy"),
    metadata={"category": "question"},
    evaluators=[
        DocumentMatches(
            pattern=r"(?im)\A(?=.*\bclimate\b)(?=.*\bstrategy\b)(?=[\s\S]*^geography::Croatia$)",
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
            pattern=r"(?i)^.*emissions reduction plan",
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
            pattern=r"(?i)^.*national energy and climate plan",
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
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.9520.0",
                "CCLW.legislative.9520.3859",
                "CCLW.legislative.9520.4620",
                # "Regulation (EU) 2023/2869" has a different family ID but is in
                # the document family on the app
                "CCLW.document.i00006386.n0000",
                "CCLW.legislative.9520.6334",
            ],
            k=5,
        ),
    ],
)

dataset.add_case(
    name="ira",
    inputs=DocumentQuery(query="ira"),
    metadata={"category": "document name+acronym"},
    evaluators=[
        Precision(
            expected=[
                "CCLW.family.10699.0",
                "CCLW.legislative.10699.5931",
                "CCLW.legislative.10699.5933",
            ],
            k=3,
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
                    "CCLW.family.10180.0",
                    "CCLW.legislative.10180.4758",
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
                    # two document pages not accessible from the family page
                    "CCLW.document.i00000772.n0000",
                    "CCLW.document.i00001516.n0000",
                    # Canada's Electric Vehicle Availability Standard, also with a
                    # document page not accessible from the family page
                    "CPR.family.i00000386.n0000",
                    "CPR.document.i00000387.n0000",
                ],
                k=5,
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
                "CCLW.document.i00006700.n0000",
                # Safeguard Mechanism (Crediting) Amendment Act 2023
                "CCLW.family.11176.0",
                "CCLW.document.i00006698.n0000",
            ],
            k=4,
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
                # Climate Action, and its initial text, amendment and consolidated version
                "CCLW.family.9492.0",
                "CCLW.legislative.9492.3806",
                "CCLW.legislative.9492.rtl_142",
                "CCLW.legislative.9492.5884",
                # Directive (EU) 2023/2413 amending as regards the promotion of
                # energy from renewable sources
                "CCLW.document.i00006233.n0000",
                # Decision (EU) 2019/504
                "CCLW.document.i00006232.n0000",
            ],
            k=6,
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
                "CCLW.document.i00008343.n0000",
            ],
            k=2,
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
    name="air pollution",
    inputs=DocumentQuery(query="air pollution", corpus="ccc"),
    metadata={"category": "topic name"},
    evaluators=[Recall(expected=["Sabin.document.121443.127392"], k=20)],
)

dataset.add_case(
    name="loss & damage finance",
    inputs=DocumentQuery(query="loss & damage finance"),
    metadata={"category": "topic name"},
    evaluators=[Recall(expected=["UNFCCC.document.i00004848.n0000"], k=20)],
)

dataset.add_case(
    name="climate finance",
    inputs=DocumentQuery(query="climate finance", topics=["Q1343"]),
    metadata={"category": "topic ranking"},
    evaluators=[
        # 254 mentions of climate finance, vs 36
        RanksAbove(
            higher="GCF.document.FP082_19920.21094",
            lower="UNFCCC.non-party.1608.0",
            k=10,
        ),
        # 597 mentions of climate finance, vs 4. On text alone the order is
        # reversed - the 4-mention document has "Climate" in its title
        RanksAbove(
            higher="GCF.document.FP086_14270.5550",
            lower="CCLW.executive.2043.2464",
            k=10,
        ),
    ],
)


def run_search(input: DocumentQuery) -> ListResponse[Document]:
    return engine.search(
        order_by=[OrderBy(field="relevance", direction="desc")],
        pagination=Pagination(page_token=1, page_size=20),
        query=input.query,
        filters=input.filters(),
    )


comparisons = Dataset[QueryPair, SearchPair, dict[str, str]](
    name="document_comparisons",
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

# These pass at msm 0.7 but fail at msm 0 (FUS-421). The two word query needs msm
# above 0.5 and the three word query above 0.67, or they still match documents
# missing one of their words
comparisons.add_case(
    name="parametric insurance",
    inputs=QueryPair(query="parametric insurance", other="parametric"),
    metadata={"category": "over-broad results"},
    evaluators=[Narrows()],
)

comparisons.add_case(
    name="parametric insurance act",
    inputs=QueryPair(query="parametric insurance act", other="parametric insurance"),
    metadata={"category": "over-broad results"},
    evaluators=[Narrows()],
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
