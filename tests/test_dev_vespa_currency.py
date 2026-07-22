"""Unit tests for query-side currency symbol normalization (FUS-79)."""

import pytest

from search.engines.dev_vespa import _normalize_currency_symbols


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("$100", "dollar100"),
        ("€50", "euro50"),
        ("£20", "pound20"),
        ("$1000", "dollar1000"),
        # Symbols map wherever they appear; the amount stays attached.
        ("budget of $100 approved", "budget of dollar100 approved"),
        ("US$100", "USdollar100"),
        # No currency symbols -> unchanged (weakAnd path is preserved).
        ("climate finance", "climate finance"),
        ("", ""),
    ],
)
def test_normalize_currency_symbols(query: str, expected: str) -> None:
    assert _normalize_currency_symbols(query) == expected
