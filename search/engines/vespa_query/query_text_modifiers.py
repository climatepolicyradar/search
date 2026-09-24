"""Query-text normalization: currency symbols, quotes, and geography aliases."""

from __future__ import annotations

import re
import unicodedata

CURRENCY_SYMBOL_REPLACEMENTS = {
    "$": "dollar",
    "€": "euro",
    "£": "pound",
}


def _normalize_currency_symbols(query: str) -> str:
    """
    Map currency symbols to words so queries match the indexed (charFiltered) form.

    This is needed as Vespa's query parser strips punctuation (incl. currency symbols)
    *before* linguistics runs, so the `passage_analysis` charFilter in
    vespa/app/services.xml - which maps these symbols to words at index time
    (e.g. "$100" -> "dollar100") - never sees them on the query side. We apply the
    same mapping to the query string here so query terms match the indexed form.

    This MUST be kept in sync with the `charFilters` block in services.xml. See FUS-79.
    """
    for symbol, word in CURRENCY_SYMBOL_REPLACEMENTS.items():
        query = query.replace(symbol, word)
    return query


def _strip_quotes(query: str) -> str:
    """
    Remove double-quote characters so the query is never parsed as an exact phrase.

    This is needed as Vespa's query parser treats `"..."` as an exact phrase (exact
    consecutive terms). We deliberately do not want to support exact match search, so
    quotes are ignored.
    """
    return query.replace('"', "")


# Geography aliases, mapping what a user types to the canonical name carried by
# the `geographies` field. Resolved in Python, before the query reaches Vespa.
#
# These used to be Lucene synonym rules (lucene-linguistics/en/geo-synonyms.txt).
# When updating these you will need to make sure you update
# `lucene-linguistics/en/geo-synonyms.txt`
# @related: LUCENE_LINGUISTICS_GEOS
# Neither side of Vespa's linguistics can express them:
#   - at query time, Vespa's query parser splits the query into independent terms
#     *before* the field analyzer runs, so `synonymGraph` sees "ivory" and "coast"
#     one at a time and a multi-word rule can never match;
#   - at index time, Vespa keeps only one token per position, so the alternatives
#     `synonymGraph` emits are silently dropped (verified against a local Vespa:
#     "czechia" expanded to "czech republic" indexed "republic" but not "czech").
# See FUS-423.
GEOGRAPHY_ALIASES = {
    "uk": "united kingdom",
    "us": "united states",
    "usa": "united states",
    "eu": "european union",
    "nz": "new zealand",
    "uae": "united arab emirates",
    "brasil": "brazil",
    "burma": "myanmar",
    "holland": "netherlands",
    "swaziland": "eswatini",
    "turkey": "turkiye",
    "south korea": "korea republic of",
    "ivory coast": "cote d'ivoire",
    "czech republic": "czechia",
    "cape verde": "cabo verde",
}

_WORD_RE = re.compile(r"\w+")

# Longest alias first, so "czech republic" is preferred over a bare "czech".
_ALIASES_LONGEST_FIRST = sorted(
    ((alias.split(), canonical) for alias, canonical in GEOGRAPHY_ALIASES.items()),
    key=lambda entry: len(entry[0]),
    reverse=True,
)


def _fold_accents(text: str) -> str:
    """Strip combining marks, mirroring the asciiFolding filter in services.xml."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )


def _resolve_geography_aliases(query: str) -> str:
    """
    Rewrite geography aliases in `query` to the canonical name, as a quoted phrase.

    Matching is on whole words, so "us" does not fire inside "thus", and longest
    alias first, so "czech republic" is not shadowed by a shorter alias. The query
    is lowercased and accent-folded for matching only, mirroring what
    `geo_analysis_search` does to the terms on the other side.

    The canonical name is emitted double-quoted so `userInput` parses it as a
    phrase. Without that, "uk" -> `united kingdom` would be two loose terms and a
    document with geography "United States" would match on "united" alone.
    """
    words = list(_WORD_RE.finditer(query))
    folded = [_fold_accents(word.group().lower()) for word in words]

    resolved: list[str] = []
    copied_to = 0
    index = 0
    while index < len(words):
        for alias_words, canonical in _ALIASES_LONGEST_FIRST:
            span = len(alias_words)
            if folded[index : index + span] != alias_words:
                continue
            resolved.append(query[copied_to : words[index].start()])
            resolved.append(f'"{canonical}"')
            copied_to = words[index + span - 1].end()
            index += span
            break
        else:
            index += 1
    resolved.append(query[copied_to:])

    return "".join(resolved)
