from prefect.task_runners import ThreadPoolTaskRunner

from prefect import flow
from relevance_tests import run_relevance_tests_parallel
from search.engines.vespa import (
    ExactVespaPassageSearchEngine,
    HybridVespaPassageSearchEngine,
)
from search.passage import Passage
from search.testcase import (
    FieldCharacteristicsTestCase,
    SearchComparisonTestCase,
    all_words_in_string,
    any_words_in_string,
)

test_cases = [
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="nz",
        characteristics_test=lambda passage: ("new zealand" in passage.text.lower())
        or ("net zero" in passage.text.lower()),  # type: ignore
        all_or_any="all",
        description="search for nz should return either new zealand or net zero in the passage text",
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
        category="BROKEN exact match",
        search_terms="adaptation options",
        # FIXME: this tests exact match search, which we don't currently consider using these tests
        # exact_match=True,
        characteristics_test=(
            lambda passage: not (
                "adaptation option" in passage.text.lower()
                and "adaptation options" not in passage.text.lower()
            )
        ),
        description="Exact match search should not perform stemming.",
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
        search_terms="nationally determined contribution",
        characteristics_test=lambda passage: "NDC" in passage.text #Maybe this should be reversed? Feels like users are more likely to search for NDC than type it out in full
        and not all_words_in_string(
            ["nationally", "determined", "contribution"], passage.text
        ),
        description="Acronyms: search for nationally determined contribution should return NDC.",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="nature-based solution",
        characteristics_test=lambda passage: "nbs" in passage.text.lower()
        and not all_words_in_string(
            ["nature", "based", "solution"], passage.text
        ),
        description="Acronyms: search for nature-based solution should return NbS.",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
        category="acronym",
        search_terms="gga",
        characteristics_test=lambda passage: all_words_in_string(["global", "goal", "adaptation"], passage.text) 
        and "gga" not in passage.text.lower(),
        description="Acronyms: search for GGA should include global goal on adaptation.",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
        FieldCharacteristicsTestCase[Passage](
        category="shortened phrase",
        search_terms="action climate empowerment", #observed a user do this and be very confused
        characteristics_test=lambda passage: "action for climate empowerment" in passage.text.lower(),
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
        characteristics_test=lambda passage: any_words_in_string(
            ["greenwashing", "green-washing", "climatewashing", "climate-washing"],
            passage.text,
        ),
        description="OR logic in search.",
        k=20,
        all_or_any="all",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
    category="related phrases",
        search_terms="EVs",
        characteristics_test=(lambda passage: "electric car" in passage.text.lower()
        and not any_words_in_string(["ev", "evs"], passage.text)),
        description="Results for closely-related phrases (EVs -> electric car) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
    category="related phrases",
        search_terms="Ecosystem-based approaches",
        characteristics_test=(lambda passage: "nbs" in passage.text.lower()
        and "ecosystem-based" not in  passage.text.lower()), #"approaches" seems pretty generic; it's the nature->ecosystem part that matters
        description="Results for closely-related phrases (Ecosystem-based approaches -> nbs) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
    category="related phrases",
        search_terms="peatland rehabilitation",
        characteristics_test=(lambda passage: all_words_in_string(["peatland", "restoration"], passage.text)
        and "rehabilitation" not in passage.text.lower()),
        description="Results for closely-related phrases (peatland rehabilitation -> peatland restoration) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
    category="related phrases",
        search_terms="human rights",
        characteristics_test=(lambda passage: "rights-based approach" in passage.text.lower() #Again not sure if this is the best order - human rights is more common
        and "human right" not in passage.text.lower()),
        description="Results for closely-related phrases (human rights -> rights-based approach) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=100,
        all_or_any="any",
        assert_results=True,
    ),
    FieldCharacteristicsTestCase[Passage](
    category="related phrases",
        search_terms="public health infrastructure",
        characteristics_test=(lambda passage: "hospital" in passage.text.lower() #Maybe these should be reversed? From a user perspective, either is plausible
        and "public health infrastructure" not in passage.text.lower()),
        description="Results for closely-related phrases (public health infrastructure -> hospital) should be found, even if the search phrase itself is not mentioned in the same paragraph",
        k=200, #This is a hard one so makes sense to increase this?
        all_or_any="any",
        assert_results=True,
    ),
]


@flow(
    name="relevance_tests_passages",
    task_runner=ThreadPoolTaskRunner(max_workers=3),  # type: ignore[arg-type]
)
def relevance_tests_passages():
    """Run relevance tests for passages"""

    engines = [
        ExactVespaPassageSearchEngine(),
        HybridVespaPassageSearchEngine(),
    ]

    run_relevance_tests_parallel(
        engines=engines,
        test_cases=test_cases,
        primitive_type=Passage,
        output_subdir="passages",
    )


if __name__ == "__main__":
    relevance_tests_passages()
