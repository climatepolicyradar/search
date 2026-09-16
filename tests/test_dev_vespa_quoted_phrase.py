"""Unit tests for splitting a query into free text + exact phrases."""

import pytest

from search.engines.dev_vespa import _parse_query


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ('UK "climate act"', ("UK", ["climate act"])),
        ('"net zero" "by 2050"', ("", ["net zero", "by 2050"])),
        ('"climate act', ("", ["climate act"])),            # unclosed trailing quote
        ('"net zero"', ("", ["net zero"])),
        ('"$100"', ("", ["$100"])),
        ('brazil "net zero" policy', ("brazil policy", ["net zero"])),
        ('climate change', ("climate change", [])),
        ('"nature-based solutions"', ("", ["nature-based solutions"])),
        ('"---"', ("", [])),                                # dropped: no alphanumerics
        ('', ("", [])),
    ],
)
def test_parse_query(query: str, expected: tuple[str, list[str]]) -> None:
    assert _parse_query(query) == expected