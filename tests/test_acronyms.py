import pytest

from search.acronyms import expansion_patterns


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
    ],
)
def test_expansion_is_found_in_text(query: str, text: str, expected: str) -> None:
    matches = [m.group(0) for p in expansion_patterns(query) for m in p.finditer(text)]
    assert matches == [expected]


def test_no_acronym_no_patterns() -> None:
    assert expansion_patterns("carbon capture") == []


def test_quoted_rules_file_is_parsed() -> None:
    # Guards the parser against a format change in documents.sr silently disabling bolding.
    assert expansion_patterns("ccs")
