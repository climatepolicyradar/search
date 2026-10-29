"""
Phrases the Vespa query-rewrite rules expand a query to, for bolding.

`vespa/app/rules/documents.sr` rewrites an acronym to EQUIV(acronym,phrase(expansion)),
and a multi-word trigger to phrase(trigger). Vespa matches the phrase but doesn't bold
it on the stemmed fields; its bolder needs a phrase's words adjacent in the raw text,
and they are not when
- the text has a stopword between them (the index drops it, the bolder does not); or
- a word is indexed with multiple stems.
So the phrases are found in the returned text and bolded here instead.
"""

import functools
import re
from pathlib import Path

_VESPA_APP = Path(__file__).resolve().parents[1] / "vespa" / "app"
_RULES = _VESPA_APP / "rules" / "documents.sr"
_STOPWORDS = _VESPA_APP / "lucene-linguistics" / "en" / "stopwords.txt"

_EQUIV_RULE = re.compile(r'^(?P<lhs>[^#+]+?)\s*\+>\s*(?P<rhs>(?:="[^"]+"\s*)+);')
_RHS_PHRASE = re.compile(r'="([^"]+)"')
_PHRASE_RULE = re.compile(r'^(?P<lhs>[^#]+?)\s*->\s*"(?P<phrase>[^"]+)"\s*;')


@functools.cache
def _expansions() -> dict[str, tuple[str, ...]]:
    """
    Rule triggers and the phrases they expand to, from rule base.

    :raises ValueError: if no rule parses, as bolding would otherwise silently
        stop covering expansions.
    """
    out: dict[str, tuple[str, ...]] = {}
    for line in _RULES.read_text().splitlines():
        if match := _EQUIV_RULE.match(line.strip()):
            phrases = tuple(_RHS_PHRASE.findall(match["rhs"]))
        elif match := _PHRASE_RULE.match(line.strip()):
            phrases = (match["phrase"],)
        else:
            continue
        for trigger in match["lhs"].split(","):
            out[trigger.strip()] = phrases
    if not out:
        raise ValueError(f"No rewrite rules parsed from {_RULES}")
    return out


@functools.cache
def _between_words() -> str:
    """
    What may sit between two words of an expansion in the raw text.

    The rules leave stopwords out of the expansion (the index drops them), so
    the text may have any number of them in between.
    """
    stopwords = [word.strip() for word in _STOPWORDS.read_text().splitlines() if word.strip()]
    return rf"\W+(?:(?:{'|'.join(map(re.escape, stopwords))})\W+)*"


@functools.cache
def _expansion_pattern(expansion: str) -> re.Pattern[str]:
    # One group per word, so each is bolded on its own and the stopwords between are not.
    # `s?` so "nationally determined contributions" is bolded, as Vespa's stemming matched it.
    words = (rf"({re.escape(word)}s?)" for word in expansion.split())
    return re.compile(rf"\b{_between_words().join(words)}\b", re.IGNORECASE)


def _fires(trigger: str, free_text: str, words: set[str]) -> bool:
    """
    Whether a rule's trigger is in the query's free text.

    A multi-word trigger is matched like an expansion, as Vespa stems the query
    before matching it: "Nature-Based Solutions" fires `nature based solution`.
    """
    if " " in trigger:
        return _expansion_pattern(trigger).search(free_text) is not None
    return trigger in words


def expansion_patterns(free_text: str) -> list[re.Pattern[str]]:
    """Patterns for the expansions of every rule the query's free text fires."""
    words = set(re.findall(r"\w+", free_text.lower()))
    return [
        _expansion_pattern(expansion)
        for trigger, expansions in _expansions().items()
        if _fires(trigger, free_text, words)
        for expansion in expansions
    ]
