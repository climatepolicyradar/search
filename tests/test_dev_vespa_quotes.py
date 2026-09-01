"""Unit tests for stripping quotes to disable exact match search"""

import pytest

from search.engines.dev_vespa import _strip_quotes


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # Quotes removed and terms preserved.
        ('"powering past coal"', "powering past coal"),
        ('"net zero"', "net zero"),
        # Partial / multiple quotes are also stripped.
        ('brazil "net zero"', "brazil net zero"),
        ('"first" and "second"', "first and second"),
        # Unbalanced quotes are stripped too.
        ('"unterminated', "unterminated"),
        # No quotes are unchanged.
        ("climate change", "climate change"),
        ("", ""),
    ],
)
def test_strip_quotes(query: str, expected: str) -> None:
    assert _strip_quotes(query) == expected