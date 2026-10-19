"""
Acronym expansions from the Vespa query-rewrite rules, for bolding.

`vespa/app/rules/documents.sr` rewrites an acronym to EQUIV(acronym,phrase(expansion)).
Vespa matches the expansion but doesn't bold it on the stemmed fields; its bolder needs
a phrase's words adjacent in the raw text, and they are not when
- the text has a stopword between them (the index drops it, the bolder does not); or
- a word is indexed with multiple stems.
So the expansions are found in the returned text and bolded here instead.
"""

import functools
import re
from pathlib import Path

_VESPA_APP = Path(__file__).resolve().parents[1] / "vespa" / "app"
_RULES = _VESPA_APP / "rules" / "documents.sr"
_STOPWORDS = _VESPA_APP / "lucene-linguistics" / "en" / "stopwords.txt"

_EQUIV_RULE = re.compile(r'^(?P<lhs>[^#+]+?)\s*\+>\s*(?P<rhs>(?:="[^"]+"\s*)+);')
_RHS_PHRASE = re.compile(r'="([^"]+)"')


@functools.cache
def _expansions() -> dict[str, tuple[str, ...]]:
    """
    Acronyms and their expansions from rule base.

    :raises ValueError: if no rule parses, as bolding would otherwise silently
        stop covering expansions.
    """
    out: dict[str, tuple[str, ...]] = {}
    for line in _RULES.read_text().splitlines():
        match = _EQUIV_RULE.match(line.strip())
        if match is None:
            continue
        phrases = tuple(_RHS_PHRASE.findall(match["rhs"]))
        for acronym in match["lhs"].split(","):
            out[acronym.strip()] = phrases
    if not out:
        raise ValueError(f"No acronym rules parsed from {_RULES}")
    return out


@functools.cache
def _between_words() -> str:
    """
    What may sit between two words of an expansion in the raw text.

    The rules leave stopwords out of the expansion (the index drops them), so
    the text may have any number of them in between.
    """
    stopwords = [w.strip() for w in _STOPWORDS.read_text().splitlines() if w.strip()]
    return rf"\W+(?:(?:{'|'.join(map(re.escape, stopwords))})\W+)*"


@functools.cache
def _expansion_pattern(expansion: str) -> re.Pattern[str]:
    # One group per word, so each is bolded on its own and the stopwords between are not.
    # `s?` so "nationally determined contributions" is bolded, as Vespa's stemming matched it.
    words = (rf"({re.escape(word)}s?)" for word in expansion.split())
    return re.compile(rf"\b{_between_words().join(words)}\b", re.IGNORECASE)


def expansion_patterns(free_text: str) -> list[re.Pattern[str]]:
    """Patterns for the expansions of every acronym in the query's free text."""
    words = set(re.findall(r"\w+", free_text.lower()))
    return [
        _expansion_pattern(expansion)
        for acronym, expansions in _expansions().items()
        if acronym in words
        for expansion in expansions
    ]
