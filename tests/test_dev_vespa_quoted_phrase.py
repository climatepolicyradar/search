"""Unit tests for detecting fully-quoted ("exact match") queries (FUS-136)."""

import pytest

from search.engines.dev_vespa import _quoted_phrase


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # Fully quoted -> the inner phrase, quotes stripped.
        ('"national strategy for climate change 2050"', "national strategy for climate change 2050"),
        ('"net zero"', "net zero"),
        ('"mango"', "mango"),
        # Surrounding whitespace is ignored.
        ('  "net zero"  ', "net zero"),
        # Inner punctuation is left for the analyzer to deal with.
        ('"$100"', "$100"),
        ('"nature-based solutions"', "nature-based solutions"),
        # Not fully quoted -> userQuery() path.
        ("climate change", None),
        ('brazil "net zero"', None),
        ('"net zero" policy', None),
        ('"first" and "second"', None),
        # Unbalanced quotes are not a phrase.
        ('"unterminated', None),
        ('trailing"', None),
        # Empty or token-less phrases would make Vespa reject the query
        # with "No query", so they fall back to userQuery().
        ('""', None),
        ('"   "', None),
        ('"---"', None),
        ('"_"', None),
        ("", None),
    ],
)
def test_quoted_phrase(query: str, expected: str | None) -> None:
    assert _quoted_phrase(query) == expected
