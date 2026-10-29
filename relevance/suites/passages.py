from dataclasses import dataclass
from enum import StrEnum, auto

from pydantic import BaseModel
from pydantic_evals import Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance.api.client import SearchClient
from relevance.api.models import (
    FieldFilter,
    Filter,
    FilteredSearchRequest,
    PassagesWithinRequest,
    SearchResponse,
)
from relevance.evaluators.evaluator import HasResults
from relevance.evaluators.forbidden import Forbidden
from relevance.evaluators.matches import Matches
from relevance.evaluators.overlap import Overlap
from relevance.evaluators.recall import Recall
from relevance.evaluators.relative_order import RanksAbove
from relevance.suites.documents import QueryPair, build_topic_filter
from search.passage import (
    Passage,
    looks_like_questionnaire,
    looks_like_reference_list,
    looks_like_short_heading,
    looks_like_table_of_contents,
)


@dataclass
class PassageMatches[I](Matches[I, Passage]):
    def text(self, result: Passage) -> str:
        """The passage's text."""
        return result.text


class Artefact(StrEnum):
    reference_list = auto()
    table_of_contents = auto()
    short_heading = auto()
    questionnaire = auto()


@dataclass
class NoArtefacts[I](Evaluator[I, HasResults[Passage], object]):
    artefact: Artefact
    k: int = 20

    def found(self, passage: Passage) -> bool:
        """Whether the passage looks like the artefact."""
        match self.artefact:
            case Artefact.reference_list:
                return looks_like_reference_list(passage)
            case Artefact.table_of_contents:
                return looks_like_table_of_contents(passage)
            case Artefact.short_heading:
                return looks_like_short_heading(passage)
            case Artefact.questionnaire:
                return looks_like_questionnaire(passage)

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasResults[Passage], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of the top k results that don't look like the artefact."""
        if top_k := ctx.output.results[: self.k]:
            found = sum(1 for result in top_k if self.found(result))
            reason = f"{found}/{len(top_k)} of top {self.k} look like {self.artefact}"
            score = (len(top_k) - found) / len(top_k)
        else:
            reason = "no results"
            score = 0.0

        return {
            "NoArtefacts": EvaluationReason(value=score, reason=reason),
            "NoArtefacts passed": EvaluationReason(
                value=score == 1.0,
                reason=reason,
            ),
        }


class PassageQuery(BaseModel):
    query: str
    topics: list[str] = []
    document_id: str | None = None
    page_size: int = 20

    def filters(self) -> Filter | None:
        """Vespa filter for the query's topics and document, or None."""
        conditions: list[FieldFilter | Filter] = []
        if topic_filter := build_topic_filter(self.topics):
            conditions.append(topic_filter)
        if self.document_id is not None:
            conditions.append(FieldFilter.contains("document_id", self.document_id))
        if not conditions:
            return None
        return Filter.and_(*conditions)


class PassagePair(BaseModel):
    first: SearchResponse[Passage]
    second: SearchResponse[Passage]


dataset = Dataset[PassageQuery, SearchResponse[Passage], dict[str, str]](
    name="passages",
    cases=[],
)

dataset.add_case(
    name="nz",
    inputs=PassageQuery(query="nz"),
    metadata={"category": "acronym"},
    evaluators=[
        PassageMatches(pattern=r"(?is)new zealand|\A(?=.*\bnet\b)(?=.*\bzero\b)|\bnz\b")
    ],
)

dataset.add_case(
    name="brazil nature based solutions",
    inputs=PassageQuery(query="brazil nature based solutions"),
    metadata={"category": "search term + geography"},
    evaluators=[
        PassageMatches(pattern=r"(?i)nature[ -]based[ -]solutions", all_or_any="any")
    ],
)

dataset.add_case(
    name="mango",
    inputs=PassageQuery(query="mango"),
    metadata={"category": "dissimilar passages excluded"},
    evaluators=[PassageMatches(pattern=r"(?i)mango")],
)

dataset.add_case(
    name="statement",
    inputs=PassageQuery(query="statement"),
    metadata={"category": "dissimilar passages excluded"},
    evaluators=[PassageMatches(pattern=r"(?i)statement")],
)

dataset.add_case(
    name="$100",
    inputs=PassageQuery(
        query="$100",
        page_size=100,
    ),
    metadata={"category": "punctuation"},
    evaluators=[
        PassageMatches(pattern=r"\$100|\$ 100|100 dollars|100 USD", k=100),
        PassageMatches(pattern=r"(?s)\A(?!.*\$1000)|\$100(?!\d)", k=100),
    ],
)

dataset.add_case(
    name="ndc",
    inputs=PassageQuery(
        query="ndc",
        page_size=100,
    ),
    metadata={"category": "acronym"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?=.*\bnationally\b)(?=.*\bdetermined\b)(?=.*\bcontribution\b)",
            k=100,
            all_or_any="any",
        ),
        PassageMatches(
            pattern=r"(?is)\A(?=.*\bnationally\b)(?=.*\bdetermined\b)(?=.*\bcontribution\b)|ndc",
            k=100,
        ),
    ],
)

dataset.add_case(
    name="nature-based solution",
    inputs=PassageQuery(
        query="nature-based solution",
        page_size=100,
    ),
    metadata={"category": "acronym"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\bnbs\b|\A(?=.*\bnature\b)(?=.*\bbased\b)(?=.*\bsolution\b)",
            k=100,
        )
    ],
)

dataset.add_case(
    name="gga",
    inputs=PassageQuery(
        query="gga",
        page_size=700,
    ),
    metadata={"category": "acronym"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?=.*\bglobal\b)(?=.*\bgoal\b)(?=.*\badaptation\b)|gga",
            k=100,
        ),
        # Some results should be about the global goal on adaptation without saying gga
        PassageMatches(
            pattern=r"(?is)\A(?!.*gga)(?=.*\bglobal\b)(?=.*\bgoal\b)(?=.*\badaptation\b)",
            k=700,
            all_or_any="any",
        ),
    ],
)

# Anne observed a user do this and be very confused
dataset.add_case(
    name="action climate empowerment",
    inputs=PassageQuery(
        query="action climate empowerment",
        page_size=100,
    ),
    metadata={"category": "shortened phrase"},
    evaluators=[
        PassageMatches(
            pattern=r"(?i)action for climate empowerment",
            k=100,
            all_or_any="any",
        )
    ],
)

dataset.add_case(
    name="enviornment",
    inputs=PassageQuery(query="enviornment"),
    metadata={"category": "misspellings"},
    evaluators=[PassageMatches(pattern=r"(?i)\benvironment\b", all_or_any="any")],
)

dataset.add_case(
    name="greenwashing permafrost",
    inputs=PassageQuery(query="greenwashing permafrost"),
    metadata={"category": "logic"},
    evaluators=[
        Recall(
            expected=[
                "019d4372-4357-77f3-b257-57c1aad30e7b",  # greenwashing only (no "permafrost")
                "019cdd99-4ad6-7a83-9813-9836dd90a51c",  # permafrost only (no "greenwashing")
            ],
            k=10,
        )
    ],
)

dataset.add_case(
    name="EVs",
    inputs=PassageQuery(
        query="EVs",
        page_size=100,
    ),
    metadata={"category": "related phrases"},
    evaluators=[PassageMatches(pattern=r"(?i)electric car", k=100, all_or_any="any")],
)

# "approaches" seems pretty generic; it's the nature->ecosystem part that matters
dataset.add_case(
    name="Ecosystem-based approaches",
    inputs=PassageQuery(
        query="Ecosystem-based approaches",
        page_size=100,
    ),
    metadata={"category": "related phrases"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?!.*ecosystem-based).*nbs",
            k=100,
            all_or_any="any",
        )
    ],
)

dataset.add_case(
    name="peatland rehabilitation",
    inputs=PassageQuery(
        query="peatland rehabilitation",
        page_size=100,
    ),
    metadata={"category": "related phrases"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?!.*rehabilitation)(?=.*\bpeatland\b)(?=.*\brestoration\b)",
            k=100,
            all_or_any="any",
        )
    ],
)

# Again not sure if this is the best order - human rights is more common
dataset.add_case(
    name="human rights in AF.document.003MTMWR.n0002",
    inputs=PassageQuery(
        query="human rights",
        document_id="AF.document.003MTMWR.n0002",
        page_size=100,
    ),
    metadata={"category": "related phrases"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?!.*human right).*rights-based approach",
            k=100,
            all_or_any="any",
        )
    ],
)

# Maybe these should be reversed? From a user perspective, either is plausible.
# This is a hard one so makes sense to increase k
dataset.add_case(
    name="public health infrastructure",
    inputs=PassageQuery(
        query="public health infrastructure",
        page_size=200,
    ),
    metadata={"category": "related phrases"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?!.*public health infrastructure).*hospital",
            k=200,
            all_or_any="any",
        )
    ],
)

# Examples
#    "CARBON FOOTPRINT 3.5.2 AND FOSSIL ENERGY BILL 3.5.2.1 - CARBON FOOTPRINT"
#    "CARBON BUDGET FOR GRUDE EMISSIONS"
#    "CARBON FOOTPRINT 2.4 AND INTERNATIONAL TRADE"
dataset.add_case(
    name="carbon in ICCN.document.i00000036.n0000",
    inputs=PassageQuery(
        query="carbon",
        document_id="ICCN.document.i00000036.n0000",
    ),
    metadata={"category": "short_headings"},
    evaluators=[NoArtefacts(artefact=Artefact.short_heading, k=3)],
)

# Examples:
#   "Gillingham, K. and K. Palmer, 2017: Bridging the Energy Efficiency
#    Gap: Policy Insights from Economic Theory and Empirical Evidence.
#    Review of Environmental Economics and Policy, 8(1), 18-38, doi:
#    10.1093/reep/ret021. Gillingham, ..."
#   "Green, J. and P. Newman, 2017b: Disruptive innovation, stranded
#    assets and forecasting: the rise and rise of renewable energy.
#    Journal of Sustainable Finance & Investment, 7(2), 169-187, ..."
# Example:
#    "System / Mitigation Option / Evidence / Agreement / Ec / Tec / Inst /
#     Soc / Env / Geo / Context / Industrial System Transitions / Energy
#     efficiency / Robust / High / Potential and adoption depend on
#     existing efficiency, energy prices and interest rates, as wel..."
dataset.add_case(
    name="energy efficiency in UNFCCC.non-party.1196.0",
    inputs=PassageQuery(
        query="energy efficiency",
        document_id="UNFCCC.non-party.1196.0",
    ),
    metadata={"category": "reference_lists, tables_of_contents"},
    evaluators=[
        NoArtefacts(artefact=Artefact.reference_list, k=10),
        NoArtefacts(artefact=Artefact.table_of_contents, k=5),
    ],
)

# Examples:
#    "Campioli, M. et al., 2015: Biomass production effciency controlled
#     by management in temperate and boreal ecosystems. Nat. Geosci., 8,
#     843-846, doi: 10.1038/ngeo2553. Campra, P., M. Garcia, ..."
#    "Zomer, R.J. et al., 2016: Global tree cover and biomass carbon on
#     agricultural land: The contribution of agroforestry to global and
#     national carbon budgets. Sci. Rep., 6, 29987. ..."
dataset.add_case(
    name="biomass in UNFCCC.non-party.1184.0",
    inputs=PassageQuery(
        query="biomass",
        document_id="UNFCCC.non-party.1184.0",
    ),
    metadata={"category": "reference_lists"},
    evaluators=[NoArtefacts(artefact=Artefact.reference_list, k=10)],
)

# Examples:
#    "United Nations Office for Disaster Risk Reduction (UNISDR). (2015).
#     Sendai Framework for Disaster Risk Reduction 2015-2030. Retrieved
#     from http://www2.ohchr.org/... United Nations (UN) ..."
#    "209 National Coordinator for Disaster Reduction (CONRED). (2010b).
#     Standard for disaster reduction number one (NRD-1). Guatemala.
#     National Coordinator for Disaster Reduction (CONRED). (2011). ..."
dataset.add_case(
    name="disaster in ICCN.document.i00000042.n0000",
    inputs=PassageQuery(
        query="disaster",
        document_id="ICCN.document.i00000042.n0000",
    ),
    metadata={"category": "reference_lists"},
    evaluators=[NoArtefacts(artefact=Artefact.reference_list, k=10)],
)

# Examples:
#    "While a thorough history of how 1.5C-2.0C became the politically
#     accepted target for policy makers and States is beyond the scope of
#     this intervention, it is available to the Court.111 Change Biology
#     5679, 5679 (2020), https://onl..."
#    "B 1 (2022), https://doi.org/10.1098/rspb.2022.0375; Wilson Thau Lym
#     Yong, et al., Seaweed: A Potential Climate Change Solution, 159
#     Renewable & Sustainable Energy Rev. 112222 (2022), ..."
dataset.add_case(
    name="nature-based solutions in Sabin.document.12109.75104",
    inputs=PassageQuery(
        query="nature-based solutions",
        document_id="Sabin.document.12109.75104",
    ),
    metadata={"category": "reference_lists"},
    evaluators=[NoArtefacts(artefact=Artefact.reference_list, k=10)],
)

# Example:
#    "Category of / Details / Indicative activities/ Modality / Targeting
#     resilience/ adaptation option / Homestead farming - support
#     vulnerable / Support to household - vegetable gardens / Provide
#     training in IPM and GAPS, via experienced service ..."
dataset.add_case(
    name="resilience in AF.document.AF00000210.n0000",
    inputs=PassageQuery(
        query="resilience",
        document_id="AF.document.AF00000210.n0000",
    ),
    metadata={"category": "tables_of_contents"},
    evaluators=[NoArtefacts(artefact=Artefact.table_of_contents, k=5)],
)

# problem - Under bm25 a passage matching "national" and "security"
#           non-adjacently scores higher on bm25(content) than the
#           true-phrase passage.
# solution - Could try raising query(prox_weight), or use a phrase operator
#            for multi-word queries so adjacency is required rather than
#            just rewarded.
dataset.add_case(
    name="national security in CPR.document.i00006724.n0000",
    inputs=PassageQuery(
        query="national security",
        document_id="CPR.document.i00006724.n0000",
    ),
    metadata={"category": "phrase_integrity"},
    evaluators=[PassageMatches(pattern=r"(?i)\bnational\W+security\b", k=2)],
)

# There are only 2 occurrences of 'hard to abate' in the search tests
dataset.add_case(
    name="hard to abate in CCLW.document.i00002502.n0000",
    inputs=PassageQuery(
        query="hard to abate",
        document_id="CCLW.document.i00002502.n0000",
    ),
    metadata={"category": "phrase_integrity"},
    evaluators=[
        PassageMatches(pattern=r"(?is)\A(?=.*\babate(ment)?\b)(?=.*\bhard\b)", k=2)
    ],
)

# problem - the top passages repeat "health". Query-intent problem
#           (public/human health vs environmental health)
# solution - None. Not expected to pass.
dataset.add_case(
    name="health in CCLW.document.i00007151.n0000",
    inputs=PassageQuery(
        query="health",
        document_id="CCLW.document.i00007151.n0000",
    ),
    metadata={"category": "low_ranking_positives"},
    evaluators=[
        Recall(
            expected=[
                # Passages talk about "public health" and "human health". A case for
                # query-rewriting?
                # rank 6 - "Environmental quality standards / Maximum permissible
                #            emission and discharge standards of pollutants / Norms for
                #            the use of fertilizers, chemical poisons, other chemical
                #            substances and maximum permissible levels of radiation..."
                "019d43a6-4293-77a1-a9bb-44e462255f55",
                # rank 11 - "8. Verification of the correctness of registration of an
                #            environmental monitoring object shall be carried out by the
                #            authorized state body. 9. Relevant ministries and
                #            departments, other bodies, nature users who..."
                "019d43a6-434a-7661-9051-dc617659598c",
            ],
            k=10,
        )
    ],
)

# TODO: checking this one with Anne
# National Carbon Emission Trading Market Power Construction Plan (2017), China
# problem - The more relevant passage has lower bm25(content)
#           (more term occurrences) and proximity_boost.
# solution - None. Not expected to pass.
dataset.add_case(
    name="carbon market in CCLW.executive.10677.5836",
    inputs=PassageQuery(
        query="carbon market",
        document_id="CCLW.executive.10677.5836",
    ),
    metadata={"category": "substantive_mention"},
    evaluators=[
        RanksAbove(
            higher="019cdce0-67ff-7030-bd7b-e971b0c20526",
            lower="019cdce0-63f6-75a2-94dc-b2d98f64a8ce",
            k=10,
        )
    ],
)

dataset.add_case(
    name="clean cooking in UNFCCC.document.i00006733.n0000",
    inputs=PassageQuery(
        query="clean cooking",
        document_id="UNFCCC.document.i00006733.n0000",
    ),
    metadata={"category": "related_phrases"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?!(?=.*\bclean\b)(?=.*\bcooking\b))(?=.*\b(stoves?|cookstoves?)\b)",
            k=10,
            all_or_any="any",
        )
    ],
)

# One ranks 2nd
dataset.add_case(
    name="higher education in CIF.document.XACTID013A.n0000",
    inputs=PassageQuery(
        query="higher education",
        document_id="CIF.document.XACTID013A.n0000",
    ),
    metadata={"category": "related_phrases"},
    evaluators=[
        PassageMatches(
            pattern=r"(?is)\A(?!(?=.*\bhigher\b)(?=.*\beducation\b))(?=.*\b(universities|university|vocational)\b)",
            k=10,
            all_or_any="any",
        )
    ],
)

# Examples:
#   higher (2) - "In 2024, we have adjusted the energy transition measure in
#                our annual scorecard ... net-zero emissions energy business"
#   lower  (0) - "[A] Our target is to maintain methane emissions intensity
#                below 0.2% and achieve near-zero methane emissions by 2030."
# The long-term solution here seems to be targets being span- or sentence-level
# classifiers – so we can detect whether the target text also contains a mention of
# renewables/methane etc.
dataset.add_case(
    name="renewable energy + target in CPR.document.i00004961.n0000",
    inputs=PassageQuery(
        query="",
        topics=["Q567", "Q1651"],  # renewable energy, target
        document_id="CPR.document.i00004961.n0000",
    ),
    metadata={"category": "topic_concept_conjunction"},
    evaluators=[
        # A renewables target should outrank a passage with a methane target, which
        # mentions renewables separately from the target.
        RanksAbove(
            higher="019d4372-7612-76f1-873e-70ee96b5e4f9",
            lower="019d4372-75f4-70c1-8bfb-ca2127383706",
            k=20,
        ),
        # A renewables target should outrank a passage that's more generically about
        # targets.
        # From Anne about giving the lower result a 0 relevance score:
        # "On the fence about this one. There are a few target-looking things
        # in here, just not really about renewables -- cutting "operational emissions"
        # only implicitly means RE. "invested in low carbon solutions" is not a target
        # and could mean lots of things.
        RanksAbove(
            higher="019d4372-7612-76f1-873e-70ee96b5e4f9",
            lower="019d4372-7574-78c0-95d6-e7af94e49977",
            k=20,
        ),
    ],
)

# Examples:
#   higher (2) - "... need for increased expansion of renewable energy in
#                order to reach the 70% target in 2030 ... additional 2 GW"
#   lower  (0) - "... electrification of society and expansion of renewable
#                energy are central to achieving the ambitious climate goals"
# problem - both tags are correct; the passages differ only in whether
#           the commitment is quantified.
# solution - Anne note while labelling: "'this passage contains two targets'
#           would be a great way to uprank".
dataset.add_case(
    name="renewable energy + target in CCLW.document.i00007832.n0000",
    inputs=PassageQuery(
        query="",
        topics=["Q567", "Q1651"],  # renewable energy, target
        document_id="CCLW.document.i00007832.n0000",
    ),
    metadata={"category": "topic_concept_conjunction"},
    evaluators=[
        RanksAbove(
            # "...The government and the parties to the agreement agree that an
            # additional 2 GW of offshore wind power must be tendered for establishment
            # before the end of 2030.."
            higher="019cb184-60cb-7743-a06a-f2b60f2dd0ce",
            # "...that electrification of society and expansion of renewable energy are
            # central to achieving the ambitious climate goals in 2030 and full climate
            # neutrality by 2050 at the latest. The parties to the agreement note that
            # a number of initiatives have been adopted to expand renewable energy
            # capacity in Denmark..."
            lower="019cb184-60cb-7743-a06a-f28cc1e95a61",
            k=10,
        )
    ],
)

# Example (0) - "Figure 19 illustrates a conceptual structure for the
#               proposed PCG. Municipal WWTW ATP Agreed Water Tariff
#               Investment Capex Project Owner Loan Loan Repayments ..."
dataset.add_case(
    name="fees and charges + tax in GCF.document.FP209_22930.15594",
    inputs=PassageQuery(
        query="",
        topics=["Q1277", "Q715"],  # fees and charges, tax
        document_id="GCF.document.FP209_22930.15594",
    ),
    metadata={"category": "topic_concept_conjunction"},
    evaluators=[Forbidden(forbidden=["019d43b0-6708-7630-bcec-dca0566302cb"], k=5)],
)

# Example (0) - the References block: "6. European Parliament and Council
#               Regulation (EU) 2018/841 ... Official Journal (OJ) L 156"
#               4,390 words, PASSAGE_LOCATION="References"
# problem - existing reference_lists tests target academic bibliographies
#           (author, year, doi). This is a legislative citation list with
#           none of those markers
# solution - could extend looks_like_reference_list for examples like this
dataset.add_case(
    name="agriculture sector + subsidy in ICCN.document.i00000027.n0000",
    inputs=PassageQuery(
        query="",
        topics=["Q786", "Q1274"],  # agriculture sector, subsidy
        document_id="ICCN.document.i00000027.n0000",
    ),
    metadata={"category": "topic_reference_lists"},
    evaluators=[NoArtefacts(artefact=Artefact.reference_list, k=5)],
)

# problem - flat topic-only score
# solution - topic ranking
dataset.add_case(
    name="fossil fuel + extreme weather in Sabin.document.14274.17897",
    inputs=PassageQuery(
        query="",
        topics=["Q638", "Q374"],  # fossil fuel, extreme weather
        document_id="Sabin.document.14274.17897",
    ),
    metadata={"category": "topic_concept_conjunction"},
    evaluators=[
        Recall(
            expected=[
                # "... bulk petroleum storage facility in New Haven, Connecticut for
                #  severe flooding and other weather-related risks ..."
                "019fb5f7-b8ba-7f61-85b7-a32e6ab16a59",
                # This doesn't explictly mention fossil fuels except for "Shell Oil", so
                # is relevant but not reliably due to be returned by search
                "019fb5f7-b8c0-7e03-abf8-54048661fa2c",
            ],
            k=5,
        )
    ],
)

# ========================================================================
# aboutness: the concept is mentioned but is not what the passage is about
# ========================================================================
# Examples:
#   higher (1) - "This Plan is informed by significant feedback ... through
#                consultations on sustainable jobs legislation"
#   lower  (0) - "The concept of 'just transition' was developed by the North
#                American trade unions movement in the 1970s ..."
# classifier - definitional passages are the densest possible match for a
#              term-of-art concept. Q47 needs a stated position on
#              defines-vs-applies, with negative_labels populated, before
#              ranking work helps.
dataset.add_case(
    name="just transition in CCLW.document.i00003205.n0000",
    inputs=PassageQuery(
        query="",
        topics=["Q47"],  # just transition
        document_id="CCLW.document.i00003205.n0000",
    ),
    metadata={"category": "topic_aboutness"},
    evaluators=[
        RanksAbove(
            higher="019cddc4-6d14-70d1-9b16-24976cdcde77",
            lower="019cddc4-6cdb-7613-8b74-c2dc68f5296f",
            k=10,
        )
    ],
)

# Examples:
#   higher (2) - "... banks can advocate for enabling conditions for
#                mobilising private sector finance for adaptation"
#   lower  (0) - "13 European Commission, 'EU Adaptation Strategy'. Accessed:
#                Jul. 02, 2025. [Online]. Available: https://..."
# TODO: add better description based on Anne explanation of scoring
dataset.add_case(
    name="adaptation finance in ICCN.document.i00000015.n0000",
    inputs=PassageQuery(
        query="",
        topics=["Q1345"],  # adaptation finance
        document_id="ICCN.document.i00000015.n0000",
    ),
    metadata={"category": "topic_aboutness, topic_reference_lists"},
    evaluators=[
        RanksAbove(
            higher="019d89e8-eaf6-7632-8dfd-ecf621f11128",
            lower="019d89e8-eaf4-7520-b80e-a6850c92589b",
            k=10,
        ),
        NoArtefacts(artefact=Artefact.reference_list, k=5),
    ],
)

# Example (0) - "Is the intervention financed partly or entirely by protein
#               crop subsidies (maximum 2% in total) ...? Tak No"
#               labeller: "Answers on a questionnaire"
# classifier - Q1829 fires on a form asking *whether* something is
#              financed. Interrogative and conditional mood should be a
#              negative signal for the concept.
# Note: questionnaires appear in 12-20% of MCF docs (by corpus type), 8% of
# Intl. agreements, 3.9% of Reports.
dataset.add_case(
    name="finance flow in CCLW.document.i00007398.n0000",
    inputs=PassageQuery(
        query="",
        topics=["Q1829"],  # finance flow
        document_id="CCLW.document.i00007398.n0000",
    ),
    metadata={"category": "topic_questionnaires"},
    evaluators=[NoArtefacts(artefact=Artefact.questionnaire, k=5)],
)

# All six judged passages labelled 0. Labeller: "None are about 'national
# security'". Matches are on "security of supply" and "energy security".
# TODO: Add derived looks_like_questionnaire penalty?
# problem - the forbidden passages contain "national security"
# solution - None. Not expected to pass.
dataset.add_case(
    name="national security + wind energy in CPR.document.i00006724.n0000",
    inputs=PassageQuery(
        query="national security",
        topics=["Q622"],  # wind energy
        document_id="CPR.document.i00006724.n0000",
    ),
    metadata={"category": "topic_phrase_integrity"},
    evaluators=[
        Forbidden(
            forbidden=[
                "019cdd4d-d20c-7f50-b58b-e466e7a44bbf",
                "019cdd4d-d237-7d00-951d-60e329fba262",
                "019cdd4d-d286-7370-84e4-44962b8b76df",
                "019cdd4d-d1d7-7bd3-a2cb-1d66174b3f48",
                "019cdd4d-d273-7c62-8981-e19c2933e86a",
                "019cdd4d-d20f-78d1-9f40-c9e14f7956df",
            ],
            k=5,
        )
    ],
)

# Positive counterpart, same keyword, different document.
dataset.add_case(
    name="national security + wind energy in Sabin.document.131799.133176",
    inputs=PassageQuery(
        query="national security",
        topics=["Q622"],  # wind energy
        document_id="Sabin.document.131799.133176",
    ),
    metadata={"category": "topic_phrase_integrity"},
    evaluators=[
        Recall(
            expected=[
                "019e907a-ee72-7381-a90a-b47ef908f5cc",
                "019e907a-ee73-7963-840f-5e4228a1041e",
            ],
            k=5,
        )
    ],
)

# Examples:
#   higher (1) - "2. In the case of marine protected areas, their management
#                extends to where the State exercises sovereignty ..."
#   lower  (0) - "Article 14. A National Park is a terrestrial, marine, or a
#                combination of both areas ..."
# problem - bm25 favours the near-duplicate definitional passages (higher "marine"
#           TF) over the substantive marine-protected-areas passage (a List, lower
#           bm25), so the specific passage sinks below a generic one.
# solution - None, expect to fail.
dataset.add_case(
    name="marine + zoning and spatial planning in CCLW.document.i00005028.n0000",
    inputs=PassageQuery(
        query="marine",
        topics=["Q1282"],  # zoning and spatial planning
        document_id="CCLW.document.i00005028.n0000",
    ),
    metadata={"category": "topic_aboutness"},
    evaluators=[
        RanksAbove(
            higher="019cd9ce-d193-74c3-82d9-6f29938b54e4",
            lower="019cd9ce-de24-7743-953e-8b3ddb86aa1f",
            k=10,
        )
    ],
)

# Example (0) - "e Official estimates exclude emissions from the combustion
#               of both aviation and marine international bunker fuels ..."
#               a footnote matching on one incidental phrase
dataset.add_case(
    name="aviation + greenhouse gas in UNFCCC.document.i00001987.n0000",
    inputs=PassageQuery(
        query="aviation",
        topics=["Q218"],  # greenhouse gas
        document_id="UNFCCC.document.i00001987.n0000",
    ),
    metadata={"category": "topic_aboutness, topic_deranking_counter_examples"},
    evaluators=[
        Recall(
            expected=[
                "019d4348-7930-7cb3-821f-80813dbaab4c",
                "019d4348-792f-7120-a806-33bf762b9a6a",
            ],
            k=5,
        ),
        Forbidden(forbidden=["019d4348-7910-7413-b3fd-46de3ae19992"], k=5),
        # "See Annex 3.2 for data by vehicle mode ... Medium- and heavy-duty truck
        # CO2 emissions increased by 75 percent from 1990 to 2021" — label 2.
        # Labeller: "Probably interested in this headline finding over the technical
        # detail".
        # NB - guards against de-ranking on a leading "See Annex/Table/Figure".
        #      The pointer is followed by the finding the user wants.
        Recall(expected=["019d4348-790f-7f42-ba94-840e3e1a4036"], k=10),
    ],
)

# "Coal extraction and handling" (relevant) vs "· coal · diesel · propane ..."
dataset.add_case(
    name="coal + fossil fuel in UNFCCC.document.i00007520.n0000",
    inputs=PassageQuery(
        query="coal",
        topics=["Q638"],  # fossil fuel
        document_id="UNFCCC.document.i00007520.n0000",
    ),
    metadata={"category": "topic_short_headings"},
    evaluators=[
        Recall(
            expected=[
                "019e88d1-94a8-7c90-9031-b30f7cf336ff",  # "Coal extraction and handling"
                "019e8a44-4864-75b1-9c6d-1d0d060e0d57",  # CIAC methodology prose
            ],
            k=5,
        ),
        Forbidden(
            forbidden=[
                # "· coal
                # · diesel
                # · propane
                # · butane petroleum coke
                # · distillation gas heavy fuel oil National Inventory Report - 2026 Edition Canada.ca/inventaire-ges"
                # type: list
                "019e8a44-124e-7b91-b772-f85f10947f1b",
            ],
            k=5,
        ),
    ],
)


def run_search(
    client: SearchClient,
    input: PassageQuery,
) -> SearchResponse[Passage]:
    return client.passages(
        FilteredSearchRequest(
            query=input.query,
            filters=input.filters(),
            page_size=input.page_size,
        )
    )


comparisons = Dataset[QueryPair, PassagePair, dict[str, str]](
    name="passage_comparisons",
    cases=[],
)

comparisons.add_case(
    name="solar power(ed)",
    inputs=QueryPair(query="solar power", other="solar powered"),
    metadata={"category": "duplicates"},
    evaluators=[Overlap(k=50, threshold=0.8)],
)

comparisons.add_case(
    name="citizen(s) assembly",
    inputs=QueryPair(query="citizen assembly", other="citizens assembly"),
    metadata={"category": "duplicates"},
    evaluators=[Overlap(k=50, threshold=0.8)],
)


def run_pair(
    client: SearchClient,
    input: QueryPair,
) -> PassagePair:
    return PassagePair(
        first=client.passages(
            FilteredSearchRequest(
                query=input.query,
                filters=None,
                page_size=50,
            )
        ),
        second=client.passages(
            FilteredSearchRequest(
                query=input.other,
                filters=None,
                page_size=50,
            )
        ),
    )

class PassagesWithinQuery(BaseModel):
    query: str
    topics: list[str] = []
    document_ids: list[str]
    msm: float = 0.0
    page_size: int = 20
    rank_profile: str | None = None


within = Dataset[PassagesWithinQuery, SearchResponse[Passage], dict[str, str]](
    name="passages_within",
    cases=[],
)

# FUS-812: within a principal document, a passage tagged with the target topic
# should outrank an untagged one that only matches the query. `search_within` ORs
# the query and the topic filter, so both stay candidates and `topic_q` is set.

within.add_case(
    name="deforestation + target in CCLW.family.9737.0",
    inputs=PassagesWithinQuery(
        query="deforestation",
        topics=["Q1651"],  # target
        document_ids=["CCLW.family.9737.0"],
    ),
    metadata={"category": "topic_concept_conjunction"},
    evaluators=[
        RanksAbove(
            higher="CCLW.executive.9737.rtl_56::89",  # tagged with target
            lower="CCLW.executive.9737.rtl_56::24",  # untagged
            k=20,
        )
    ],
)


def run_search_within(
    client: SearchClient,
    input: PassagesWithinQuery,
) -> SearchResponse[Passage]:
    return client.passages_within(
        PassagesWithinRequest(
            query=input.query,
            filters=build_topic_filter(input.topics),
            document_ids=input.document_ids,
            msm=input.msm,
            page_size=input.page_size,
            rank_profile=input.rank_profile,
        )
    )
