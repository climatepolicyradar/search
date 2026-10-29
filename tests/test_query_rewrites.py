import pytest

from search.query_rewrites import expansion_patterns


@pytest.mark.parametrize(
    ("query", "text", "expected"),
    [
        pytest.param(
            "CCS",
            "Launched carbon capture and storage (CCS)",
            "carbon capture and storage",
            id="stopword-gap",
        ),
        pytest.param(
            "ccs policy",
            "Carbon-Capture-and-Storage",
            "Carbon-Capture-and-Storage",
            id="hyphenated",
        ),
        pytest.param(
            "NDC",
            "our Nationally Determined Contributions",
            "Nationally Determined Contributions",
            id="two-stems-plural",
        ),
        pytest.param(
            "gga",
            "the global goal on adaptation",
            "global goal on adaptation",
            id="gap-on",
        ),
        pytest.param(
            "EV", "electric vehicle uptake", "electric vehicle", id="comma-lhs"
        ),
        pytest.param(
            "nature based solutions",
            "namely: nature-based solutions, improving knowledge.",
            "nature-based solutions",
            id="phrase-rule",
        ),
        pytest.param(
            "Nature-Based Solution's",
            "Federal Action Plan on Nature-Based Solutions",
            "Nature-Based Solutions",
            id="phrase-rule-possessive-query",
        ),
        pytest.param(
            "nature based solutions",
            "a nature based solution's benefits",
            "nature based solution",
            id="phrase-rule-possessive-text",
        ),
        pytest.param(
            "brazil nature based solutions",
            "Nature-based solutions in Brazil",
            "Nature-based solutions",
            id="phrase-rule-among-other-words",
        ),
    ],
)
def test_expansion_is_found_in_text(query: str, text: str, expected: str) -> None:
    matches = [
        match.group(0)
        for pattern in expansion_patterns(query)
        for match in pattern.finditer(text)
    ]
    assert matches == [expected]


def test_no_acronym_no_patterns() -> None:
    assert expansion_patterns("carbon capture") == []


def test_phrase_rule_does_not_fire_on_its_words_out_of_order() -> None:
    assert expansion_patterns("solutions based on nature") == []


def test_phrase_is_not_found_with_its_words_out_of_order() -> None:
    patterns = expansion_patterns("nature based solutions")
    assert patterns
    assert not any(
        pattern.search("Solutions based on the best evidence will protect nature.")
        for pattern in patterns
    )


def test_quoted_rules_file_is_parsed() -> None:
    # Guards the parser against a format change in documents.sr silently disabling bolding.
    assert expansion_patterns("ccs")
