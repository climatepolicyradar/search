from dataclasses import dataclass

from pydantic_evals import Dataset

from api.routers import settings
from relevance.evaluators.forbidden import Forbidden
from relevance.evaluators.matches import Matches
from relevance.evaluators.precision import Precision
from relevance.evaluators.recall import Recall
from search.engines import ListResponse, OrderBy, Pagination
from search.engines.dev_vespa.labels_search_engine import DevVespaLabelSearchEngine
from search.label import LabelSearchResult


@dataclass
class LabelMatches[I](Matches[I, LabelSearchResult]):
    def text(self, result: LabelSearchResult) -> str:
        """The label's value and alternative labels, one per line."""
        return "\n".join([result.value, *result.alternative_labels])


GEO_AUSTRALIA = "geography::AUS"
GEO_BRAZIL = "geography::BRA"
GEO_CANADA = "geography::CAN"
GEO_CHINA = "geography::CHN"
GEO_COLOMBIA = "geography::COL"
GEO_CROATIA = "geography::HRV"
GEO_JAPAN = "geography::JPN"
GEO_NEW_SOUTH_WALES = "geography::AU-NSW"
GEO_NEW_ZEALAND = "geography::NZL"
GEO_PHILIPPINES = "geography::PHL"
GEO_SWEDEN = "geography::SWE"
GEO_USA = "geography::USA"

CONCEPT_ADAPTATION_FINANCE = "concept::Q1345"
CONCEPT_AIR_POLLUTION_RISK = "concept::Q412"
CONCEPT_BAN = "concept::Q1285"
CONCEPT_EXTREME_WEATHER = "concept::Q374"
CONCEPT_FOSSIL_FUEL = "concept::Q638"
CONCEPT_INDIGENOUS_PEOPLE = "concept::Q684"
CONCEPT_JUST_TRANSITION = "concept::Q47"
CONCEPT_NET_ZERO_TARGET = "concept::Q1653"
CONCEPT_SUBSIDY = "concept::Q1274"
CONCEPT_SUBSIDY_REMOVAL = "concept::Q1275"
CONCEPT_TARGET = "concept::Q1651"


dataset = Dataset[str, ListResponse[LabelSearchResult], dict[str, str]](
    name="labels",
    cases=[],
)

dataset.add_case(
    name="brazil",
    inputs="brazil",
    metadata={"category": "place name"},
    evaluators=[Precision(expected=[GEO_BRAZIL], k=1)],
)

dataset.add_case(
    name="new south wales",
    inputs="new south wales",
    metadata={"category": "place name"},
    evaluators=[
        Precision(
            expected=[
                GEO_AUSTRALIA,
                GEO_NEW_SOUTH_WALES,
            ],
            k=2,
        ),
    ],
)

for query in ["united", "states"]:
    dataset.add_case(
        name=query,
        inputs=query,
        metadata={"category": "place name"},
        evaluators=[Recall(expected=[GEO_USA], k=10)],
    )

for query in ["united states", "united states of america"]:
    dataset.add_case(
        name=query,
        inputs=query,
        metadata={"category": "place name"},
        evaluators=[Precision(expected=[GEO_USA], k=1)],
    )

dataset.add_case(
    name="Philippines policies in climate changes",
    inputs="Philippines policies in climate changes",
    metadata={"category": "place name + other terms"},
    evaluators=[
        Precision(
            expected=[
                GEO_PHILIPPINES,
                "party::Philippines",
                "entity_type::Policy",
                "academic/research::Climate Policy",
                "type::Policies",
                "keyword::Climate Change",
                "focal_area::Climate Change",
            ],
            k=7,
        ),
    ],
)

dataset.add_case(
    name="brazil nature based solutions",
    inputs="brazil nature based solutions",
    metadata={"category": "place name + other terms"},
    evaluators=[Recall(expected=[GEO_BRAZIL], k=3)],
)

# NOTE: this test matches a pattern rather than using IDs, because we have lots of
# energy-related concepts but one specifically for 'energy'. I.e. we want to test for
# concepts that have 'energy' in them.
dataset.add_case(
    name="energy policy act us",
    inputs="energy policy act us",
    metadata={"category": "document name"},
    evaluators=[
        # 'energy'/'polic' are deliberate prefix matches, but 'act' is a whole word, as a
        # substring it also accepts 'Climate Action', 'extraction', 'practice'
        LabelMatches(pattern=r"(?i)energy|polic|usa|\bact\b", k=10, all_or_any="all"),
    ],
)

# "dummy996" # CLIMATE
dataset.add_case(
    name="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
    inputs="Law No. 018/2022 ratifying Ordinance No. 019/PR/2021 relating to climate change",
    metadata={"category": "document name"},
    evaluators=[Recall(expected=["entity_type::Law"], k=3)],
)

# Not so sure about this one. There might be a few labels that are relevant
# but not included eg "law and plan"
dataset.add_case(
    name="national climate plan",
    inputs="national climate plan",
    metadata={"category": "document name"},
    evaluators=[
        Precision(
            expected=[
                "entity_type::Nationally determined contribution",
                "entity_type::National adaptation plan",
                "entity_type::National adaptation plan,adaptation communication",
                "entity_type::National drought plan (ndp)",
                "entity_type::National biodiversity strategy and action plan (nbsap)",
                "entity_type::National target (nt)",
                "entity_type::Plan",
                "keyword::National Energy And Climate Plans",
            ],
            k=8,
        ),
    ],
)

dataset.add_case(
    name="nz",
    inputs="nz",
    metadata={"category": "entity name"},
    evaluators=[
        Precision(
            expected=[
                CONCEPT_NET_ZERO_TARGET,
                GEO_NEW_ZEALAND,
            ],
            k=2,
        ),
    ],
)

# dataset.add_case(
#     name="totalenergies",
#     inputs="totalenergies",
#     metadata={"category": "entity name"},
#     evaluators=[Precision(expected=["dummy933"], k=1)],  # TOTAL ENERGIES
# )

# dataset.add_case(
#     name="european court of human rights",
#     inputs="european court of human rights",
#     metadata={"category": "entity name"},
#     evaluators=[Precision(expected=["dummy932"], k=1)],  # ECHR
# )

dataset.add_case(
    name="How many targets does Canada currently have relating to climate change?",
    inputs="How many targets does Canada currently have relating to climate change?",
    metadata={"category": "question"},
    evaluators=[
        Precision(
            expected=[
                CONCEPT_TARGET,
                GEO_CANADA,
                "party::Canada",
                "focal_area::Climate Change",
                "keyword::Climate Change",
            ],
            k=5,
        ),
    ],
)

dataset.add_case(
    name="what is the croatias climate strategy",
    inputs="what is the croatias climate strategy",
    metadata={"category": "question"},
    evaluators=[
        Precision(
            expected=[
                "non-party::Climate Strategies",
                "entity_type::Policy",
                "entity_type::Strategy",
                GEO_CROATIA,
                "party::Croatia",
            ],
            k=5,
        ),
    ],
)

# TODO: 'hurricanes' is a label of storm, which is a child of 'extreme weather'.
# So this requires the labels of the subconcepts to be indexed. They should probably
# be indexed in a different field to the main concept's labels.
# "6etq43sc",  # storm (we don't have a classifier for this)
dataset.add_case(
    name="hurricanes",
    inputs="hurricanes",
    metadata={"category": "topic"},
    evaluators=[Recall(expected=[CONCEPT_EXTREME_WEATHER], k=5)],
)

dataset.add_case(
    name="fossil fuel subsidy removal",
    inputs="fossil fuel subsidy removal",
    metadata={"category": "topic"},
    evaluators=[
        Precision(
            expected=[
                CONCEPT_FOSSIL_FUEL,
                CONCEPT_SUBSIDY_REMOVAL,
                "keyword::Fossil Fuels Subsidies",
            ],
            k=3,
        ),
        Recall(expected=[CONCEPT_SUBSIDY_REMOVAL], k=10),
        Forbidden(forbidden=[CONCEPT_SUBSIDY], k=10),
    ],
)

dataset.add_case(
    name="Just transition",
    inputs="Just transition",
    metadata={"category": "topic"},
    evaluators=[Precision(expected=[CONCEPT_JUST_TRANSITION], k=1)],
)

dataset.add_case(
    name="resilient infrastructure",
    inputs="resilient infrastructure",
    metadata={"category": "topic not in kg"},
    evaluators=[
        LabelMatches(pattern="(?i)resilien|infrastructur|construct", all_or_any="any"),
    ],
)

dataset.add_case(
    name="offshore wind roadmap",
    inputs="offshore wind roadmap",
    metadata={"category": "topic not in kg"},
    evaluators=[
        LabelMatches(pattern="(?i)wind|energy|roadmap", all_or_any="any"),
    ],
)

dataset.add_case(
    name="phase out",
    inputs="phase out",
    metadata={"category": "topic"},
    evaluators=[
        # ban is the parent concept of phase-out
        Precision(expected=[CONCEPT_BAN], k=1),
        # subsidy removal ranks highly due to 'phasing out of subsidies' aliases
        Forbidden(forbidden=[CONCEPT_SUBSIDY_REMOVAL], k=5),
    ],
)

dataset.add_case(
    name="Adaptation (OR) resilience investment",
    inputs="Adaptation (OR) resilience investment",
    metadata={"category": "logic"},
    evaluators=[Precision(expected=[CONCEPT_ADAPTATION_FINANCE], k=1)],
)

dataset.add_case(
    name="japan + united states + sweden + china",
    inputs="japan + united states + sweden + china",
    metadata={"category": "logic"},
    evaluators=[
        Precision(
            expected=[
                GEO_JAPAN,
                GEO_USA,
                GEO_SWEDEN,
                GEO_CHINA,
                "party::United States",
                "party::Sweden",
                "party::Japan",
                "party::Japan ",
                "party::japan",
                "party::China",
            ],
            k=10,
        ),
    ],
)

dataset.add_case(
    name="indigenous people + colombia + laws",
    inputs="indigenous people + colombia + laws",
    metadata={"category": "logic"},
    evaluators=[
        Precision(
            expected=[
                CONCEPT_INDIGENOUS_PEOPLE,
                "keyword::Indigenous People",
                GEO_COLOMBIA,
                "party::Colombia",
                "entity_type::Law",
            ],
            k=5,
        ),
    ],
)

dataset.add_case(
    name="air",
    inputs="air",
    metadata={"category": "topic"},
    evaluators=[Recall(expected=[CONCEPT_AIR_POLLUTION_RISK], k=10)],
)

for query in ["air pollution", "air pollution risk", "pollution risk", "air pol"]:
    dataset.add_case(
        name=query,
        inputs=query,
        metadata={"category": "topic"},
        evaluators=[Recall(expected=[CONCEPT_AIR_POLLUTION_RISK], k=5)],
    )


def run_search(input: str) -> ListResponse[LabelSearchResult]:
    return DevVespaLabelSearchEngine(settings=settings).search(
        order_by=[OrderBy(field="relevance", direction="desc")],
        pagination=Pagination(page_token=1, page_size=20),
        query=input,
    )
