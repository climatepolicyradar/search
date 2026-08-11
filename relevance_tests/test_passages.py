from prefect.task_runners import ThreadPoolTaskRunner

from api.routers import settings
from prefect import flow
from relevance_tests import run_relevance_tests_parallel
from search.engines.dev_vespa import DevVespaPassageSearchEngine

#from search.engines.vespa import (
#    ExactVespaPassageSearchEngine,
#    HybridVespaPassageSearchEngine,
#)
from search.passage import Passage
from search.testcase import (
    FieldCharacteristicsTestCase,
    RecallTestCase,
    RelativeOrderTestCase,
    SearchComparisonTestCase,
    all_words_in_string,
    any_words_in_string,
    phrase_in_string,
)

test_cases = [
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="nz",
        characteristics_test=lambda passage: ("new zealand" in passage.text.lower())
        or all_words_in_string(["net", "zero"], passage.text)  # type: ignore
        or any_words_in_string(["nz"], passage.text),
        all_or_any="all",
        description="search for nz should return new zealand, net zero or nz in the passage text",
        assert_results=True,
    ),
    SearchComparisonTestCase[Passage](
        category="duplicates",
        search_terms="solar power",
        search_terms_to_compare="solar powered",
        description="Compare single vs duplicated search terms (solar power vs solar powered).",
        k=50,
        minimum_overlap=0.8,
        strict_order=False,
    ),
    SearchComparisonTestCase[Passage](
        category="duplicates",
        search_terms="citizen assembly",
        search_terms_to_compare="citizens assembly",
        description="Compare single vs duplicated search terms (citizen assembly vs citizens assembly).",
        k=50,
        minimum_overlap=0.8,
        strict_order=False,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="search term + geography",
        search_terms="brazil nature based solutions",
        characteristics_test=lambda passage: "nature based solutions"
        in passage.text.lower().replace("-", " "),
        all_or_any="any",
        description="Search for 'brazil nature based solutions' returns passages which mention nature based solutions",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="exact match",
        search_terms='"national strategy for climate change 2050"',
        characteristics_test=lambda passage: "national strategy for climate change 2050"
        in passage.text.lower(),
        description="Search in quotes should perform an exact match search.",
        k=100,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="dissimilar passages excluded",
        search_terms="mango",
        characteristics_test=(lambda passage: "mango" in passage.text.lower()),
        description="Dissimilar passages to 'mango' should be excluded.",
        k=20,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="dissimilar passages excluded",
        search_terms="statement",
        characteristics_test=(lambda passage: "statement" in passage.text.lower()),
        description="Dissimilar passages to 'statement' should be excluded.",
        k=20,
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="punctuation",
        search_terms="$100",
        characteristics_test=lambda passage: any(
            phrase in passage.text
            for phrase in ["$100", "$ 100", "100 dollars", "100 USD"]
        ),
        description="Search for $100 should always return $100.",
        k=100,
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="punctuation",
        search_terms="$100",
        characteristics_test=lambda passage: not (
            "$1000" in passage.text and "$100" not in passage.text
        ),
        description="Exact match search for $100 should not return $1000.",
        k=100,
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="ndc",
        characteristics_test=lambda passage: all_words_in_string(
        ["nationally", "determined", "contribution"], passage.text
        ),
        description="Acronyms: search for NDC should return nationally determined contribution (check rule fires).",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="ndc",
        characteristics_test=lambda passage: all_words_in_string(
            ["nationally", "determined", "contribution"], passage.text
        )
        or "ndc" in passage.text.lower(),
        description="Acronyms: search for NDC should return nationally determined contribution or NDC.",
        k=100,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="nature-based solution",
        characteristics_test=lambda passage: all_words_in_string(["nbs"], passage.text)
        or all_words_in_string(["nature", "based", "solution"], passage.text),
        description="Acronyms: search for nature-based solution should return NbS.",
        k=100,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="gga",
        characteristics_test=lambda passage: all_words_in_string(
            ["global", "goal", "adaptation"], passage.text
        )
        or "gga" in passage.text.lower(),
        description="Acronyms: search for GGA should include global goal on adaptation.",
        k=100,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="shortened phrase",
        # Anne observed a user do this and be very confused
        search_terms="action climate empowerment",
        characteristics_test=lambda passage: "action for climate empowerment"
        in passage.text.lower(),
        description="shortened phrase: leaving out 'for' in 'action for climate empowerment' should still return the passage",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="misspellings",
        search_terms="enviornment",
        characteristics_test=lambda passage: all_words_in_string(
            ["environment"], passage.text
        ),
        description="Search for misspelled text (environment).",
        k=20,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="logic",
        search_terms="green-washing or greenwashing or climatewashing or climate-washing",
        characteristics_test=lambda passage: any(
            term in passage.text.lower().replace("-", "")
            for term in ["greenwashing", "climatewashing"]
        ),
        description="OR logic in search.",
        k=20,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="related phrases",
        search_terms="EVs",
        characteristics_test=(
            lambda passage: "electric car" in passage.text.lower()
            and not any_words_in_string(["ev", "evs"], passage.text)
        ),
        description="Results for closely-related phrases (EVs -> electric car) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    # TODO: add query-rewrite rule for acronym expansion
    FieldCharacteristicsTestCase[Passage](
        category="related phrases",
        search_terms="Ecosystem-based approaches",
        characteristics_test=(
            lambda passage: "nbs" in passage.text.lower()
            and "ecosystem-based" not in passage.text.lower()
        ),  # "approaches" seems pretty generic; it's the nature->ecosystem part that matters
        description="Results for closely-related phrases (Ecosystem-based approaches -> nbs) should be found, even if the search phrase itself is not mentioned in the same paragraph",
            # problem - in absence of semantics would need query re-write rule for nature->ecosystem,
            #           then another step to go nature->nbs, but 'ecosystem based approaches' and 
            #           'nature based solutions' are not synonymous so a re-write rule is not appropriate.
            # solution - future work either on concepts or query expansion
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="related phrases",
        search_terms="peatland rehabilitation",
        characteristics_test=(
            lambda passage: all_words_in_string(
                ["peatland", "restoration"], passage.text
            )
            and "rehabilitation" not in passage.text.lower()
        ),
        description="Results for closely-related phrases (peatland rehabilitation -> peatland restoration) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="related phrases",
        search_terms="human rights",
        characteristics_test=(
            lambda passage: "rights-based approach"
            in passage.text.lower()  # Again not sure if this is the best order - human rights is more common
            and "human right" not in passage.text.lower()
        ),
        description="Results for closely-related phrases (human rights -> rights-based approach) should be found, even if the search phrase itself is not mentioned in the same paragraph",
            # problem - all k =100 contain "human right"
            # solution - filter on a document that contains "rights-based approach" so 
            #            that the test works as expected
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    # TODO: use document filter on document containing "rights-based approach" so that the test works as expected
    FieldCharacteristicsTestCase[Passage](
        category="related phrases",
        search_terms="public health infrastructure",
        characteristics_test=(
            lambda passage: "hospital"
            in passage.text.lower()  # Maybe these should be reversed? From a user perspective, either is plausible
            and "public health infrastructure" not in passage.text.lower()
        ),
        description="Results for closely-related phrases (public health infrastructure -> hospital) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=200,  # This is a hard one so makes sense to increase this
        all_or_any="any",
        assert_results=True,
    ),
    # Examples
    #    "CARBON FOOTPRINT 3.5.2 AND FOSSIL ENERGY BILL 3.5.2.1 - CARBON FOOTPRINT"
    #    "CARBON BUDGET FOR GRUDE EMISSIONS"
    #    "CARBON FOOTPRINT 2.4 AND INTERNATIONAL TRADE"
    FieldCharacteristicsTestCase[Passage](
        category="short_headings",
        search_terms="carbon",
        document_id="ICCN.document.i00000036.n0000",
        characteristics_test=lambda passage: not passage.looks_like_short_heading,
        all_or_any="all",
        k=3,
        assert_results=True,
        description=(
            "ALLCAPS figure titles ('CARBON BUDGET FOR GRUDE EMISSIONS') must not "
            "occupy the top 3."
        ),
    ),
    # Examples:
    #   "Gillingham, K. and K. Palmer, 2017: Bridging the Energy Efficiency
    #    Gap: Policy Insights from Economic Theory and Empirical Evidence.
    #    Review of Environmental Economics and Policy, 8(1), 18-38, doi:
    #    10.1093/reep/ret021. Gillingham, ..."
    #   "Green, J. and P. Newman, 2017b: Disruptive innovation, stranded
    #    assets and forecasting: the rise and rise of renewable energy.
    #    Journal of Sustainable Finance & Investment, 7(2), 169-187, ..."
    FieldCharacteristicsTestCase[Passage](
        category="reference_lists",
        search_terms="energy efficiency",
        document_id="UNFCCC.non-party.1196.0",
        characteristics_test=lambda passage: not passage.looks_like_reference_list,
        all_or_any="all",
        k=10,
        assert_results=True,
        description=(
            "Bibliography blocks must not be returned in the top 10 results"
        ),
    ),
    # Examples:
    #    "Campioli, M. et al., 2015: Biomass production effciency controlled
    #     by management in temperate and boreal ecosystems. Nat. Geosci., 8,
    #     843-846, doi: 10.1038/ngeo2553. Campra, P., M. Garcia, ..."
    #    "Zomer, R.J. et al., 2016: Global tree cover and biomass carbon on
    #     agricultural land: The contribution of agroforestry to global and
    #     national carbon budgets. Sci. Rep., 6, 29987. ..."
    FieldCharacteristicsTestCase[Passage](
        category="reference_lists",
        search_terms="biomass",
        document_id="UNFCCC.non-party.1184.0",
        characteristics_test=lambda passage: not passage.looks_like_reference_list,
        all_or_any="all",
        k=10,
        assert_results=True,
        description=(
            "Bibliography blocks must not be returned in the top 10 results"
        ),
    ),
    #
    # Examples:
    #    "United Nations Office for Disaster Risk Reduction (UNISDR). (2015).
    #     Sendai Framework for Disaster Risk Reduction 2015-2030. Retrieved
    #     from http://www2.ohchr.org/... United Nations (UN) ..."
    #    "209 National Coordinator for Disaster Reduction (CONRED). (2010b).
    #     Standard for disaster reduction number one (NRD-1). Guatemala.
    #     National Coordinator for Disaster Reduction (CONRED). (2011). ..."
    FieldCharacteristicsTestCase[Passage](
        category="reference_lists",
        search_terms="disaster",
        document_id="ICCN.document.i00000042.n0000",
        characteristics_test=lambda passage: not passage.looks_like_reference_list,
        all_or_any="all",
        k=10,
        assert_results=True,
        description=(
            "Bibliography blocks must not be returned in the top 10 results"
        ),
    ),
    #
    # Examples:
    #    "While a thorough history of how 1.5C-2.0C became the politically
    #     accepted target for policy makers and States is beyond the scope of
    #     this intervention, it is available to the Court.111 Change Biology
    #     5679, 5679 (2020), https://onl..."
    #    "B 1 (2022), https://doi.org/10.1098/rspb.2022.0375; Wilson Thau Lym
    #     Yong, et al., Seaweed: A Potential Climate Change Solution, 159
    #     Renewable & Sustainable Energy Rev. 112222 (2022), ..."
    FieldCharacteristicsTestCase[Passage](
        category="reference_lists",
        search_terms="nature-based solutions",
        document_id="Sabin.document.12109.75104",
        characteristics_test=lambda passage: not passage.looks_like_reference_list,
        all_or_any="all",
        k=10,
        assert_results=True,
        description=(
            "Bibliography blocks must not be returned in the top 10 results"
        ),
    ),
    #
    # Example:
    #    "Category of / Details / Indicative activities/ Modality / Targeting
    #     resilience/ adaptation option / Homestead farming - support
    #     vulnerable / Support to household - vegetable gardens / Provide
    #     training in IPM and GAPS, via experienced service ..."
    FieldCharacteristicsTestCase[Passage](
        category="tables_of_contents",
        search_terms="resilience",
        document_id="AF.document.AF00000210.n0000",
        characteristics_test=lambda passage: not passage.looks_like_table_of_contents,
        all_or_any="all",
        k=5,
        assert_results=True,
        description=(
            "Table-of-contents blocks must not reach the top 5. "
        ),
    ),
    # Example:
    #    "System / Mitigation Option / Evidence / Agreement / Ec / Tec / Inst /
    #     Soc / Env / Geo / Context / Industrial System Transitions / Energy
    #     efficiency / Robust / High / Potential and adoption depend on
    #     existing efficiency, energy prices and interest rates, as wel..."
    FieldCharacteristicsTestCase[Passage](
        category="tables_of_contents",
        search_terms="energy efficiency",
        document_id="UNFCCC.non-party.1196.0",
        characteristics_test=lambda passage: not passage.looks_like_table_of_contents,
        all_or_any="all",
        k=5,
        assert_results=True,
        description=(
            "Table-of-contents blocks must not reach the top 5. "
        ),
    ),
    FieldCharacteristicsTestCase[Passage](
        category="phrase_integrity",
        search_terms="national security",
        document_id="CPR.document.i00006724.n0000",
        characteristics_test=lambda passage: phrase_in_string(
            "national security", passage.text
        ),
        all_or_any="all",
        k=2,
        assert_results=True,
        description=(
            "Multi-word queries must not match on a subset or reordering of terms in the top 2."
        ),
    ),
    FieldCharacteristicsTestCase[Passage](
        category="phrase_integrity",
        search_terms="hard to abate",
        document_id="CCLW.document.i00002502.n0000",
        characteristics_test=lambda passage: any_words_in_string(
            ["abate", "abatement"], passage.text
        )
        and all_words_in_string(["hard"], passage.text),
        all_or_any="all",
        k=2,
        assert_results=True,
        description=(
            # There are only 2 occurrences of 'hard to abate' in the search tests
            "'hard to abate' must not degrade to 'abatement' alone in the top 2."
        ),
    ),
    RecallTestCase[Passage](
        category="low_ranking_positives",
        search_terms="carbon",
        # 2025 Annual Report – "Reinvigorating climate action in the face of worsening impacts and weakened leadership"
        document_id="ICCN.document.i00000036.n0000",
        expected_result_ids=[
            # rank 9 - "The carbon sink decreases during El Nino events, due to
            #            megafires (Canada, Siberia, Amazon), and extreme droughts.
            #            Since 2015, CO2 absorption north of the 20th parallel has
            #            halved, and 2024 marks a record level of tropical forest..."
            "019d89e9-0ddd-7593-bfb3-4549d0a4deea",
            # rank 11 - "Due to carbon losses from cultivated and artificialized
            #            soils, the second carbon budget for the land use, land-use
            #            change and forestry (LULUCF) sector has not been met. With
            #            an average carbon sink of -36 Mt CO2 eq per year..."
            "019d89e9-0dd7-7e01-9292-94219530df5d",
            # rank 16 - "The LULUCF carbon sink deteriorated significantly between
            #            2013 and 2017, falling from -50.2 to -28.1 Mt CO2e, a
            #            decrease of 45%. The maintenance of this carbon sink at an
            #            average level of -36 Mt CO2 eq since 2018..."
            "019d89e9-0dd8-70e0-9985-4cfea5689d83",
        ],
        k=5,
        description=(
            "The three passages quantifying France's LULUCF carbon budget should "
            "reach the top 5."
            # problem - passages that quantify the LULUCF carbon budget ranking above 
            #.          passages that discuss carbon generally is a judgement with no 
            #           lexical correlation i.e. there is not enough intent in the 
            #           search query to really understand relevance
            # solution - Aspirational. Not expected to pass.
        ),
    ),
    # TODO: relax test to k=20?
    RecallTestCase[Passage](
        category="low_ranking_positives",
        search_terms="health",
        document_id="CCLW.document.i00007151.n0000",
        expected_result_ids=[
            # Passages talk about "public health" and "human health". A case for query-
            # rewriting?
            
            # rank 14 - "Environmental quality standards / Maximum permissible
            #            emission and discharge standards of pollutants / Norms for
            #            the use of fertilizers, chemical poisons, other chemical
            #            substances and maximum permissible levels of radiation..."
            "019d43a6-4293-77a1-a9bb-44e462255f55",
            # rank 17 - "8. Verification of the correctness of registration of an
            #            environmental monitoring object shall be carried out by the
            #            authorized state body. 9. Relevant ministries and
            #            departments, other bodies, nature users who..."
            "019d43a6-434a-7661-9051-dc617659598c",
        ],
        k=10,
        description=(
            "Public-health provisions of the Tajik Ecological Code should reach the "
            "top 10."
            # problem - Ranks 1-4 are type Lists, highly ranked on repeated occurrences
            #           of “health”.
            # solution - None yet. We want to make the lists into better passages for
            #            search rather than de-rank them.
        ),
    ),
    # TODO: checking this one with Anne
    RecallTestCase[Passage](
        category="low_ranking_positives",
        search_terms="biomass",
        document_id="UNFCCC.non-party.1184.0",
        expected_result_ids=[
            # rank 9 - "However, forests may become less resilient to heat stress in
            #            future due to the long recovery period required to replace
            #            lost biomass and the projected increased frequency of heat
            #            and drought events (Frank et al. 2015a; McDowell and Allen..."
            #            NB: this is the citation-dense PROSE that a naive 'et al.'
            #            or doi-based reference filter would wrongly discard.
            "019d437a-5ba0-7f20-a5ad-3e5f3ffe685f",
            # rank 13 - "Furthermore, fire emissions during 1997-2016 were dominated
            #            by savanna (65.3%), followed by tropical forest (15.1%),
            #            boreal forest (7.4%), temperate forest (2.3%), peatland
            #            (3.7%) and agricultural waste burning (6.3%)..."
            "019d437a-5bb2-7e20-8d1b-80761a664711",
        ],
        k=10,
        description=(
            "Substantive biomass prose should outrank the chapter bibliography. "
            # problem - rank 10 is a bibliography entry, which we can de-rank, but 
            #           second passage still below substantive passages.
            # rank 10 - Lamers, P., and M. Junginger, 2013: The "debt" is in the detail:
            #           A synthesis of recent temporal forest carbon analyses on woody 
            #           biomass for energy. Biofuels, Bioprod. Biorefining, 7, 373-385, 
            #           doi:10.1002/bbb.1407.
            # solution - de-rank bibliography/reference_item (in addition to existing 
            #            looks_like_reference_list). Maybe just have the one passage 
            #            required to pass the test as the other passages in the top 10
            #            look substantive.
        ),
    ),
    # TODO: remove second passage from test? de-rank bibliography/reference item
    RecallTestCase[Passage](
        category="low_ranking_positives",
        search_terms="disaster",
        # Climate Change Report Guatemala
        document_id="ICCN.document.i00000042.n0000",
        expected_result_ids=[
            # rank 16 - "119 In extreme cases, adaptation measures to climate-related
            #            disasters tend to be reactive and short-sighted, rather than
            #            proactive. This is the case for families who, due to a lack
            #            of economic resources, have decided to withdraw their
            #            children from school..."
            "019d89e9-01d5-7be2-b1b1-460afdbf3f40",
        ],
        k=10,
        description=(
            "Discussion of reactive disaster adaptation should reach the top 10"
            # problem - rank 3 and rank 10 are author biographies, rank 5 is a `Table`,
            #           rank 6 is a `list` (heading).
            # solution - de-rank biographies/authors and we want to make tables and 
            #            lists into better passages for search rather than de-rank them.
        ),
    ),
    # TODO: de-rank biographies/authors
    RelativeOrderTestCase[Passage](
        category="substantive_mention",
        search_terms="carbon market",
        # National Carbon Emission Trading Market Power Construction Plan (2017), China
        document_id="CCLW.executive.10677.5836",
        higher_result_id="019cdce0-67ff-7030-bd7b-e971b0c20526",
        lower_result_id="019cdce0-63f6-75a2-94dc-b2d98f64a8ce",
        k=10,
        description=(
            "A passage talking about carbon markets directly should rank above one which only describes enabling conditions for carbon markets."
            # problem - The more relevant passage has higher nativeRank but lower 
            #           nativeProximity; the more relevant passage defines what the
            #           national carbon emissions trading market is uses the literal 
            #           phrase once, where as the less relevant passage mentions carbon 
            #           markets repeatedly so has higher nativeProximity and ranks higher.
            # solution - We could try reducing the weight of nativeProximity to not
            #            inflate rank from phrase repetition, but that could risk the 
            #            work done to date on the whole phrase ranking above a partial 
            #            phrase, so leaving as is. Try adding weight of nativeFieldRank.
        ),
    ),
    FieldCharacteristicsTestCase[Passage](
        category="related_phrases",
        search_terms="clean cooking",
        document_id="UNFCCC.document.i00006733.n0000",
        characteristics_test=lambda passage: any_words_in_string(
            ["stove", "stoves", "cookstove", "cookstoves"], passage.text
        )
        and not all_words_in_string(["clean", "cooking"], passage.text),
        all_or_any="any",
        k=10,
        assert_results=True,
        description=(
            "'clean cooking' should match passages about efficient cook stoves "
            "without the literal phrase."
        ),
    ),
    FieldCharacteristicsTestCase[Passage](
        category="related_phrases",
        search_terms="higher education",
        document_id="CIF.document.XACTID013A.n0000",
        characteristics_test=lambda passage: any_words_in_string(
            ["universities", "university", "vocational"], passage.text
        )
        and not all_words_in_string(["higher", "education"], passage.text),
        all_or_any="any",
        k=10,
        assert_results=True,
        description=(
            "'higher education' should match passages naming universities or "
            "vocational institutions without the literal phrase. One ranks 2nd."
        ),
    ),
]


@flow(
    name="relevance_tests_passages",
    task_runner=ThreadPoolTaskRunner(max_workers=3),  # type: ignore[arg-type]
)
def relevance_tests_passages():
    """Run relevance tests for passages"""

    engines = [
        DevVespaPassageSearchEngine(settings=settings, debug=True),
        #ExactVespaPassageSearchEngine(),
        #HybridVespaPassageSearchEngine(),
    ]

    run_relevance_tests_parallel(
        engines=engines,
        test_cases=test_cases,
        primitive_type=Passage,
        output_subdir="passages",
    )


if __name__ == "__main__":
    relevance_tests_passages()
