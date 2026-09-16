"""Unit tests for query-side geography alias resolution (FUS-423)."""

import pytest

from search.engines.dev_vespa import GEOGRAPHY_ALIASES, _resolve_geography_aliases


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # Multi-word aliases - the ones Lucene synonyms could never match, because
        # Vespa's query parser splits the query before the analyzer runs.
        ("ivory coast", '"cote d\'ivoire"'),
        ("czech republic", '"czechia"'),
        ("south korea", '"korea republic of"'),
        ("cape verde", '"cabo verde"'),
        # Single-word aliases, previously handled by geo-synonyms.txt.
        ("uk", '"united kingdom"'),
        ("usa", '"united states"'),
        ("turkey", '"turkiye"'),
        # Aliases resolve wherever they appear, and the rest of the query is kept
        # verbatim so the free-text clauses are unaffected.
        ("UK Climate Change Act", '"united kingdom" Climate Change Act'),
        ("ivory coast climate law", '"cote d\'ivoire" climate law'),
        ("energy policy act us", 'energy policy act "united states"'),
        # Matching is on whole words, so short aliases don't fire inside longer ones.
        ("thus we must act", "thus we must act"),
        ("nzone", "nzone"),
        ("ukraine", "ukraine"),
        # Case and accents are folded for matching only.
        ("Ivory Coast", '"cote d\'ivoire"'),
        ("TURKEY", '"turkiye"'),
        # A canonical name is already canonical - left alone rather than re-resolved.
        ("Côte d'Ivoire", "Côte d'Ivoire"),
        # Nothing to resolve -> unchanged.
        ("climate finance", "climate finance"),
        ("", ""),
    ],
)
def test_resolve_geography_aliases(query: str, expected: str) -> None:
    assert _resolve_geography_aliases(query) == expected


def test_longest_alias_wins() -> None:
    """
    "czech republic" must not be shadowed by a shorter overlapping alias.

    Ordering is by alias length, so adding a single-word alias that prefixes a
    multi-word one can't silently break the longer rule.
    """
    assert _resolve_geography_aliases("czech republic") == '"czechia"'
    assert _resolve_geography_aliases("south korea") == '"korea republic of"'


def test_aliases_are_lowercase_and_unaccented() -> None:
    """
    Matching folds the query, so an alias key that isn't already folded is dead.

    This pins the invariant rather than the current contents of the table.
    """
    for alias in GEOGRAPHY_ALIASES:
        assert alias == alias.lower(), f"alias {alias!r} must be lowercase"
        assert alias.isascii(), f"alias {alias!r} must be unaccented ASCII"
