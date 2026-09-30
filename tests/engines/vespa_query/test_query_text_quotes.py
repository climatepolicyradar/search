"""Unit tests for splitting a query into free text + exact phrases."""

import pytest

from search.engines.vespa_query.query_text_modifiers import _parse_query, _strip_quotes


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ('UK "climate act"', ("UK", ["climate act"])),
        ('"net zero" "by 2050"', ("", ["net zero", "by 2050"])),
        ('"climate act', ("", ["climate act"])),  # unclosed trailing quote
        ('"net zero"', ("", ["net zero"])),
        ('"$100"', ("", ["$100"])),
        ('brazil "net zero" policy', ("brazil policy", ["net zero"])),
        ("climate change", ("climate change", [])),
        ('"nature-based solutions"', ("", ["nature-based solutions"])),
        ('"---"', ("", [])),
        ("", ("", [])),
    ],
)
def test_parse_query(query: str, expected: tuple[str, list[str]]) -> None:
    assert _parse_query(query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ('"powering past coal"', "powering past coal"),
        ('brazil "net zero"', "brazil net zero"),
        ('"unterminated', "unterminated"),
        ("climate change", "climate change"),
        ("", ""),
    ],
)
def test_strip_quotes(query: str, expected: str) -> None:
    assert _strip_quotes(query) == expected
