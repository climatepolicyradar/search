"""
Passage-type detectors for the `looks_like_*` fields on `passages`.

Vendored from `search/passage.py` in the repo root. The feeder builds from a
Docker context of `vespa-feeder/` alone and installs no dependency on the
`search` package, so the rulesets cannot be imported here - they are copied.
Kept verbatim apart from taking `text` / `page_numbers` instead of a `Passage`,
so the two files stay diffable: **change both, or neither**.

Stdlib only, deliberately - nothing here needs a dependency.
"""

import re
from collections.abc import Callable

_MONTH = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
# 'December 31, 2024' or '31 December 2024' - a calendar date, not a citation year.
_CALENDAR_DATE = re.compile(
    rf"\b(?:{_MONTH})[a-z]*\.?\s+\d{{1,2}},?\s+\d{{4}}"
    rf"|\b\d{{1,2}}\s+(?:{_MONTH})[a-z]*\.?,?\s+\d{{4}}"
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
# An author initial: 'J.' but not the '2.' of '1.A.2.' or the 'A.1' of an outline.
_AUTHOR_INITIAL = re.compile(r"(?<![.\d])\b[A-Z]\.(?!\d)")
# A year closing a citation: '(2019).', '(n.d.):', ', 2018.', '. 1997.'
_CITATION_YEAR = re.compile(
    r"\(\s*(?:n\.d\.|\d{4}[a-z]?)\s*\)\s*[.,:]|,\s*\d{4}[a-z]?\s*[.:]|\.\s\d{4}[a-z]?\."
)
# Where to find the source: a DOI, a URL, or an access note.
_SOURCE_LOCATOR = re.compile(
    r"doi:|doi\.org|https?://|ftp://|(?<![/.])\bwww\.|Retrieved"
    r"|Available (?:at|from|online)|Accessed|last visited|In press|ISSN|ISBN",
    re.IGNORECASE,
)
# Contact details, which mark a signature block or supplier directory - both of
# which are as dense in initials and periods as a bibliography is.
_CONTACT_DETAIL = re.compile(
    r"@|Tel[.:]|Telephone|Teléfono|Fax|E-?mail|Correo", re.IGNORECASE
)
# The words prose is made of. Reference entries are titles and names, and use
# far fewer of them.
_FUNCTION_WORD = re.compile(
    r"\b(?:the|of|and|to|in|that|which|for|with|as|by|is|are|was|will|be|been"
    r"|this|these|has|have|from|on|at|it|its|not|but|their|our)\b",
    re.IGNORECASE,
)

# Citation signals are counted per 100 words; a signal counts as present at two
# occurrences per 100 words, i.e. once every fifty words. The rates are strongly
# bimodal - on the validation set the median negative scores 0 on every one of
# them - so anything from 1 to 2 scores the same, and 2 is taken because it also
# rejects a passage carrying a single stray initial.
_SIGNAL_PER_100_WORDS = 2.0
_MIN_CITATION_SIGNALS = 2
# Periods per 100 words. Reference entries are chopped into abbreviated fields;
# prose runs a whole sentence between periods. Hand-labelled 10th percentile for
# reference lists: 15.7.
_DENSE_PERIODS_PER_100_WORDS = 18.0
# Function words per 100 words. Hand-labelled median: 14 for reference lists, 27
# for everything else. This is the guard against prose with a couple of
# 'Available at' footnotes glued to the end of it.
_PROSE_FUNCTION_WORDS_PER_100_WORDS = 25.0
_CONTACTS_PER_100_WORDS = 1.0

# Above this many words, per-100-word rates are reliable, because they average many entries'
# titles against each other; below it, the same signals switch from rate to bare presence. See
# the docstring below for why lowering the rate threshold does not fix this instead.
_DENSITY_MIN_WORDS = 60

# A leading footnote or endnote marker before the citation proper: '58 ', '(1) ', '[4] ', '99. '
_FOOTNOTE_MARKER = re.compile(r"^\(?\[?\d{1,4}\]?\)?[.)]?\s+")
# A full URL or DOI token, not just the keyword `_SOURCE_LOCATOR` triggers on - used to measure
# how much text is left once a short passage's own locator is stripped out of it.
_FULL_LOCATOR_TOKEN = re.compile(r"(?:https?|ftp)://\S+|www\.\S+|doi:\s*\S+", re.IGNORECASE)
# Below this many leftover words, a short passage carrying a source locator is essentially JUST
# the locator (a bare 'Available at: <url>' footnote) - sufficient on its own, since these carry
# no author-initial or citation-year at all and could never otherwise reach two signals.
_MAX_WORDS_AROUND_BARE_LOCATOR = 10
# The bare-locator shortcut only fires on these content types. A bare URL in a page header or
# footer is as often the document's own repeating self-referential permalink or an e-signature
# verification link as it is a genuine citation - textually indistinguishable, but pageHeader
# and pageFooter carry no other signal to disambiguate them, so the shortcut is withheld there
# rather than guessed at.
_BARE_LOCATOR_CONTENT_TYPES = frozenset({"Text", "footnote"})
# Below the density floor, citation-year and source-locator are the two signals specific enough
# to citations that at least one of them is required; author-initial and period-density alone
# are not, because they also fire on section headings, outline markers and signature blocks -
# see docstring. Source-locator only counts towards this when content_type is safe, for the
# same self-referential-URL reason the bare-locator shortcut below is restricted.
_MIN_SHORT_SIGNALS = 2


def looks_like_reference_list(text: str, content_type: str = "") -> bool:
    """
    True if the passage is a bibliography, endnote or numbered footnote block.

    Covers a full list of several entries, or as few as one.

    Reads as: above a density floor, it is a reference list if it does not read as prose, is
    not a contact block, and at least two of four named citation signals hold *at density*.
    Below that floor, the same four signals are checked for bare presence instead, two of them
    (period-density kept, the prose veto dropped) are enough, and a passage that is essentially
    just a locator ('Available at: <url>') is sufficient on its own.

    Requiring *two* signals at density is what does the work above the floor. Any one of them
    alone fires on far too much - a URL in a footnote, a date in a table, an initial in a
    signature block - but a passage carrying two of author initials, citation years, source
    locators and period density is a citation list and almost nothing else. Dropping to one
    signal takes precision from 1.00 to 0.86; demanding three takes recall from 0.98 to 0.86.

    Calendar dates are stripped before counting: the ', 2024.' of 'December 31,
    2024.' is otherwise indistinguishable from a citation year.

    Unlike `looks_like_table_of_contents`, there is no positional condition here.
    Reference lists sit at a median 0.62 of the way through their document against
    0.55 for everything else - the distributions are the same, because numbered
    footnote citations appear on every page rather than only at the end.

    Below `_DENSITY_MIN_WORDS`, per-100-word rates stop being reliable, and not for the reason
    it looks like. It is not sampling noise from a small denominator - a real single citation,
    checked by hand, scores 27.6% on the prose-veto rate against a 25% cutoff, genuinely over
    the line. The rate was calibrated on whole reference-list PASSAGES, where one entry's
    unusually wordy title is averaged against many terser ones in the same passage; applied to
    a single entry, there is no averaging to smooth out that one title's own idiosyncratic word
    choice, so the same cutoff that works well on an average of many entries does not transfer
    to any one entry. Lowering the rate threshold does not fix this either - it trades the false
    negatives this causes for false positives on genuinely prose-heavy short passages instead.

    So below the floor, the prose veto is dropped rather than loosened, and precision is
    recovered a different way: by presence rather than rate, and by requiring one of the two
    citation-specific signals (citation-year, source-locator) rather than accepting any two of
    the four interchangeably.

    Two other thresholds were tried and rejected first, both found by tracing real
    disagreements and then checking every validation set built so far, not just the trace:

    - Two of any four signals (the long-path rule, reused as-is) worked on the curated,
      hand-labelled sample but not on a genuinely random one: real false positives turned up in
      `List`-typed content, all three carried by the exact same pair - author-initial plus
      period-density, with neither citation-year nor source-locator present - a section heading
      ('IV. DISCUSSION E. Article III Standing'), a page-number artifact, and a flattened
      map-legend row credited to its authors' initials.
    - Raising the bar to three of any four fixed those, but broke two long-standing hand-picked
      test fixtures in the process: 'Hansen, J., 2003: Can we defuse the global warming time
      bomb?' (the ticket's own motivating shape) has only author-initial and citation-year - two
      signals, not three - and a real two-entry footnote citation block has only source-locator
      and period-density. Both are genuine citations wrongly excluded by a threshold tuned
      against a different failure mode; neither showed up in the Snowflake-derived validation
      sets used to check the three-of-four change, only in this file's own older fixtures.

    The pattern across every case checked, good and bad, is the same: author-initial and
    period-density fire on section headings, outline markers and signature blocks just as
    readily as on citations, so two of *only those two* is not evidence of anything; but
    citation-year and source-locator are specific enough that either one, paired with any second
    signal, reliably is. Hence: two of the four, with at least one being citation-year or
    source-locator. Period-density stays a rate rather than switching to presence, because it
    holds up fine even at these lengths.

    Source-locator does not count towards that requirement in `pageHeader`/`pageFooter` content,
    for the same self-referential-URL reason the bare-locator shortcut below is restricted
    there. Citation-year carries no equivalent ambiguity and is accepted regardless of content
    type.

    A bare-locator shortcut exists separately from the rule above, because footnotes that are
    essentially just 'Available at: <url>' or a bare DOI carry no author-initial and no
    citation-year at all, and so could never otherwise reach two signals no matter how the
    thresholds are tuned. It is restricted to `_BARE_LOCATOR_CONTENT_TYPES` - only `Text` and
    `footnote` - because a bare URL in a page header or footer is at least as often the
    document's own repeating CDN permalink or an electronic-signature verification link as it is
    a genuine citation, and the two are textually indistinguishable. A held-out, hand-labelled
    disagreement sample measured this directly rather than assuming it away: of 40 passages this
    shortcut newly caught in `pageHeader`/`pageFooter` on a fresh random draw, only 23 were
    genuine citations - the rest were self-referential permalinks and 'Electronically signed
    by:' verification blocks. This is not a low-stakes mislabelling either: nothing else in the
    ranking pipeline filters or de-ranks page-furniture content types, so an incorrect flag here
    is not a redundant penalty on content that would have ranked poorly regardless - checked
    directly against `vespa/app/schemas/passages.sd` and the query-building code, neither
    conditions on `content_type` anywhere. An e-signature block occasionally arrives typed as
    plain `footnote` rather than `pageFooter`, in which case content-type gating cannot catch it
    - a known remaining gap, not chased further since fixing it would mean pattern-matching the
    signature phrasing itself rather than anything content-type can distinguish.

    Deliberately NOT conditions here, having turned out to be dead weight once two
    signals are required:

    - an explicit ALLCAPS REFERENCES / BIBLIOGRAPHY heading, which never changed a
      verdict on the validation set - passages carrying one always had two other
      signals anyway;
    - publication furniture ('pp. 14', 'vol. 3', 'eds.', 'ibid', 'supra'), which
      cost precision, because legal prose is full of it;
    - parenthetical author-year citations ('(Lal, 2016)'), the hallmark of the
      IPCC-style prose we want to KEEP. The function-word veto already excludes
      that prose, so counting them a second time added nothing;
    - 'et al.', which is more frequent per 100 words in the prose we want to keep
      (3.6) than in the reference lists we want to drop (1.7);
    - an organisation-name-plus-year opener ('World Bank (2022)') as a fifth short-passage
      signal - tried during development and reverted, because it frequently fires off the
      exact same text as the citation-year signal (the comma right after a closing parenthesis
      satisfies both), so it was not meaningfully independent of a signal already counted;
    - reusing `looks_like_short_heading` or the table-of-contents detector's `_DATA_CELL` to
      veto the `List` false positives directly - tried, and neither actually matched them (the
      section heading is only ~54% uppercase, well under `looks_like_short_heading`'s 90% bar,
      and the map-legend row mixes numbers with category words like 'Urban', failing
      `_DATA_CELL`'s figures-only match).

    Dropping publication furniture has a known cost: a block of legal footnotes
    carrying URLs, 'Id.' and 'supra' scores just under all four thresholds and so
    fires no signal at all. A membership/registration-number signature block
    ('No. 016750N For M. C. Bhandari & Co. ... Partner') is excluded correctly, but only
    incidentally: it carries author-initial and period-density, the same insufficient pair as
    the `List` false positives above, and neither citation-year nor source-locator, so it falls
    out of the same rule rather than needing its own veto.

    Scored against `research/passage_type_detectors/data/reflist_validation_set.jsonl`
    (original strata): P=1.000, R=0.920 - up from the previously-shipped P=1.000, R=0.828.
    Scored against `research/passage_type_detectors/data/reference_item_validation_set.jsonl`,
    built for single/small reference items specifically: P=0.979, R=0.712. Scored against
    `research/passage_type_detectors/data/reflist_fresh_disagreement.jsonl` - every disagreement
    between this version and the previously-shipped one, hand-labelled, across two fresh,
    genuinely random 1,800-passage draws (not keyword-targeted - see
    `research/passage_type_detectors/reflist_firing_rate_sample.sql`): P=0.960, R=0.750. The two
    remaining false positives there are the `footnote`-typed e-signature block described above,
    and a citation whose footnote marker opens the passage but is followed by substantial
    unrelated body prose - a chunking artifact, not a ruleset gap.

    WARNING: Claude figured out the below ruleset based on a labelled sample of
    the data. It should be flexible enough for use, but should be used with caution in
    production applications.
    """
    text = _CALENDAR_DATE.sub(" ", text)
    words = _WORD.findall(text)
    if not words:
        return False

    def per_100_words(pattern: re.Pattern) -> float:
        return len(pattern.findall(text)) / len(words) * 100

    if len(words) >= _DENSITY_MIN_WORDS:
        reads_as_prose = per_100_words(_FUNCTION_WORD) > _PROSE_FUNCTION_WORDS_PER_100_WORDS
        is_contact_block = per_100_words(_CONTACT_DETAIL) >= _CONTACTS_PER_100_WORDS
        if reads_as_prose or is_contact_block:
            return False

        citation_signals = [
            # 'Hansen, J.,' / 'J. Hansen', repeatedly - one stray 'Dr. C. Mark Eakin'
            # in a litigation paragraph is not enough
            per_100_words(_AUTHOR_INITIAL) >= _SIGNAL_PER_100_WORDS,
            # '(2019).' closing an entry
            per_100_words(_CITATION_YEAR) >= _SIGNAL_PER_100_WORDS,
            # 'doi:10...', 'Retrieved from https://...'
            per_100_words(_SOURCE_LOCATOR) >= _SIGNAL_PER_100_WORDS,
            # abbreviated fields rather than sentences
            text.count(".") / len(words) * 100 >= _DENSE_PERIODS_PER_100_WORDS,
        ]
        return sum(citation_signals) >= _MIN_CITATION_SIGNALS

    if _CONTACT_DETAIL.search(text):
        return False

    remainder = _FULL_LOCATOR_TOKEN.sub("", _FOOTNOTE_MARKER.sub("", text, count=1))
    if (
        content_type in _BARE_LOCATOR_CONTENT_TYPES
        and _SOURCE_LOCATOR.search(text)
        and len(_WORD.findall(remainder)) <= _MAX_WORDS_AROUND_BARE_LOCATOR
    ):
        return True

    citation_year_present = bool(_CITATION_YEAR.search(text))
    source_locator_present = bool(_SOURCE_LOCATOR.search(text))
    short_signals = [
        bool(_AUTHOR_INITIAL.search(text)),
        citation_year_present,
        source_locator_present,
        text.count(".") / len(words) * 100 >= _DENSE_PERIODS_PER_100_WORDS,
    ]
    has_strong_signal = citation_year_present or (
        source_locator_present and content_type in _BARE_LOCATOR_CONTENT_TYPES
    )
    return sum(short_signals) >= _MIN_SHORT_SIGNALS and has_strong_signal


# A line holding nothing but a page number or a roman-numeral folio.
_LOCATOR_LINE = re.compile(
    r"^[\s.·\-–—]*(\d{1,3}|[ivxlcdm]{1,8}|[IVXLCDM]{1,8})[\s.·]*$"
)
# A line holding nothing but a section number: 3.2.1, but not the decimal 9.00.
_SECTION_NUMBER_LINE = re.compile(r"^\(?\d{1,2}(?:\.[1-9]\d?){2,}\.?\)?$")
# A table cell holding only figures, symbols or an inventory notation key.
_DATA_CELL = re.compile(
    r"^(?:[\d\s.,;:%()\[\]<>≤≥=+\-–—/*'\"$€£¥&]+"
    r"|(?:NE|NO|NA|N/A|IE|NC|C|X|nil|na|-|—|–|\.)\.?)$",
    re.I,
)
# A title followed by the page it is on: 'Executive Summary .... 14', 'Annex B 7'.
_TRAILING_LOCATOR = re.compile(
    r"[A-Za-z\)]\.?[\s.·]+(\d{1,3}|[ivxlcdm]{2,8}|[IVXLCDM]{1,8})\.?$"
)
# An entry opening with hierarchical section numbering: '3.2 Baseline', '(1.4)'.
_HIERARCHICAL = re.compile(r"^\(?\d{1,2}(?:\.[1-9]\d?)+\.?\)?(?:\s+[A-Za-z(]|$)")
# An entry opening with a flat label: '4. Findings', 'B) Scope', 'Annex III'.
_FLAT_NUMBER = re.compile(
    r"^(?:\d{1,2}[.)]?|[IVXLCDM]{1,5}[.)]|[A-Za-z][.)]|\((?:[a-z]|[ivx]{1,4}|\d{1,2})\))\s+\S"
    r"|^(?:chapter|annex|annexe|appendix|appendices|section|part|volume)\s+[\dIVXLCA-Z]",
    re.I,
)
# The passage names itself as an index of something.
_FRONT_MATTER = re.compile(
    r"table of contents|^\s*contents\b|list of (?:tables|figures|acronyms|abbreviations|"
    r"annexes|appendices|boxes)|table of authorities",
    re.I | re.M,
)
# The standard sections a report's contents listing points at.
_TOC_ENTRY_WORD = re.compile(
    r"\b(?:foreword|preface|acknowledge?ments?|executive summary|introduction|conclusions?|"
    r"references|bibliography|glossary|annexe?|appendix|abbreviations|acronyms|"
    r"chapter|section|summary|overview|background)\b",
    re.I,
)
# A sentence boundary mid-line: the mark of running prose, not of a title.
_PROSE = re.compile(r"[.?;:]\s+[a-z]")
# A line that closes like a sentence rather than like a title.
_SENTENCE_END = re.compile(r"[.;:,]$")
# A line broken off mid-clause, i.e. a wrapped table cell or paragraph.
_MID_CLAUSE_END = re.compile(r"[;,:]$")
_EQUALS = re.compile(r"=")
_ROMAN_DIGITS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

_MIN_LINES = 4
_MIN_ENTRIES = 5
# Share of entries that must be short and free of mid-line sentence boundaries.
_TITLE_LIKE_SHARE = 0.75
_TITLE_MAX_WORDS = 25
# A long entry that also closes like a sentence is real content; a long contents
# entry is a wrapped title and carries no terminal punctuation.
_SENTENCE_MIN_WORDS = 15
_SENTENCE_SHARE = 0.30
# Above this share of pure figure/symbol lines the passage is a data table.
_DATA_CELL_SHARE = 0.25
_MID_CLAUSE_SHARE = 0.20
_EQUATION_SHARE = 0.20
# Signature thresholds, as a share of entries.
_HIERARCHICAL_SHARE = 0.35
_STANDARD_SECTION_SHARE = 0.25
_FLAT_NUMBER_SHARE = 0.65
_PAGE_NUMBER_SHARE = 0.40
# Share of trailing page numbers that must follow a distinct title. Without this,
# a table header block reading 'Sector 1 / Sector 2 / Sector 3' is a perfect
# ascending page column.
_DISTINCT_TITLE_SHARE = 0.80
# Front matter is at the front. On a fresh sample of passages this single veto
# removed 11 of the 12 false positives the text signals produced, while keeping
# every contents listing, which is why it is worth the per-chapter listings it
# costs (see the docstring).
_FRONT_MATTER_MAX_PAGE = 10


def _folio(token: str) -> int | None:
    """The integer value of an arabic or roman page number, else None."""
    if token.isdigit():
        return int(token)
    total = largest = 0
    for char in reversed(token.lower()):
        value = _ROMAN_DIGITS.get(char)
        if value is None:
            return None
        total += -value if value < largest else value
        largest = max(largest, value)
    return total


def _never_goes_backwards(values: list[int]) -> bool:
    """
    True if a run of page numbers never decreases.

    Page numbers climb down a contents listing, whereas the bare integers at the
    end of a table row are in no particular order.
    """
    return all(b >= a for a, b in zip(values, values[1:]))


def looks_like_table_of_contents(text: str, page_numbers: list[int]) -> bool:
    """
    True if the passage is a contents listing or other front-matter locator index.

    Reads as: it is a contents listing if it sits in the document's front matter,
    is a block of at least five title-like entries, is not a data table or
    wrapped prose, and carries at least one of five positive signatures.

    Lines are first sorted into page-number folios, standalone section numbers,
    pure data cells and entries, because a parsed contents listing arrives with
    its page column split onto its own lines and those lines must not be judged
    as entries.

    Fragmentary short lines are NOT on their own a usable signal: that describes
    every parsed table, and it is why the previous version of this fired on half
    of all multi-line passages. It is a gate here rather than a signature.
    Entries ending in a period are common rather than disqualifying - that period
    is usually a dot leader the parser swallowed.

    The page veto is the single most effective condition and the only one that
    does not read `text`. It is skipped when `page_numbers` is empty.

    Collapsed contents listings (a whole TOC on one line, no newlines) are not
    detected: they are indistinguishable here from prose carrying a 'Table of
    Contents' running-header artefact.

    WARNING: Claude figured out the below ruleset from a labelled sample of the
    data. It should be flexible enough for use here, but should be used with caution.

    TODO: we may be able to rely on passage types once they're in the index
    (specifically looking for list/table). See FUS-158.
    """
    if page_numbers and min(page_numbers) > _FRONT_MATTER_MAX_PAGE:
        return False

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < _MIN_LINES:
        return False

    folios: list[int] = []
    sections, data, entries = [], [], []
    for line in lines:
        locator = _LOCATOR_LINE.match(line)
        if _SECTION_NUMBER_LINE.match(line):
            sections.append(line)
        elif locator and (page := _folio(locator.group(1))):
            folios.append(page)  # there is no page zero
        elif locator or _DATA_CELL.match(line):
            data.append(line)
        else:
            entries.append(line)
    if len(entries) < _MIN_ENTRIES:
        return False

    def share_of_entries(predicate: Callable[[str], object]) -> float:
        return sum(1 for line in entries if predicate(line)) / len(entries)

    # Gate: the entries have to look like titles before anything else is worth
    # asking.
    entries_are_title_like = (
        share_of_entries(
            lambda line: len(line.split()) <= _TITLE_MAX_WORDS
            and not _PROSE.search(line)
        )
        >= _TITLE_LIKE_SHARE
    )
    if not entries_are_title_like:
        return False

    # Vetoes: any one of these means the passage is a table or a paragraph that
    # merely happens to be chopped into short lines.
    is_mostly_data_cells = len(data) / len(lines) > _DATA_CELL_SHARE
    entries_read_as_sentences = (
        share_of_entries(
            lambda line: len(line.split()) > _SENTENCE_MIN_WORDS
            and _SENTENCE_END.search(line)
        )
        >= _SENTENCE_SHARE
    )
    entries_end_mid_clause = (
        share_of_entries(_MID_CLAUSE_END.search) >= _MID_CLAUSE_SHARE
    )
    entries_contain_equations = share_of_entries(_EQUALS.search) >= _EQUATION_SHARE
    if (
        is_mostly_data_cells
        or entries_read_as_sentences
        or entries_end_mid_clause
        or entries_contain_equations
    ):
        return False

    # The page numbers a contents listing puts at the end of its entries, and the
    # titles they follow.
    trailing_page_numbers: list[int] = []
    titles: set[str] = set()
    for line in entries:
        match = _TRAILING_LOCATOR.search(line)
        if match and (page := _folio(match.group(1))):
            trailing_page_numbers.append(page)
            titles.add(line[: match.start(1)].rstrip(" .·"))

    # Signatures: any one is enough.
    names_itself_an_index = bool(_FRONT_MATTER.search(text))
    is_hierarchically_numbered = (
        sum(1 for line in entries if _HIERARCHICAL.match(line)) + len(sections)
    ) / len(entries) >= _HIERARCHICAL_SHARE
    names_standard_sections = (
        share_of_entries(_TOC_ENTRY_WORD.search) >= _STANDARD_SECTION_SHARE
    )
    is_flatly_numbered = share_of_entries(_FLAT_NUMBER.match) >= _FLAT_NUMBER_SHARE
    entries_end_in_climbing_page_numbers = (
        len(trailing_page_numbers) / len(entries) >= _PAGE_NUMBER_SHARE
        and len(titles) / len(trailing_page_numbers) >= _DISTINCT_TITLE_SHARE
        and _never_goes_backwards(trailing_page_numbers)
    )

    return (
        names_itself_an_index
        or is_hierarchically_numbered
        or names_standard_sections
        or is_flatly_numbered
        or entries_end_in_climbing_page_numbers
    )


def looks_like_short_heading(text: str, content_type: str = "") -> bool:
    """
    True if the passage is a short ALLCAPS figure title or section heading.
    
    Fewer than 12 words and either at least 90% of the cased characters are upper case or 
    type is `sectionHeading`.
    """
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if not words or len(words) >= 12:
        return False

    if content_type == "sectionHeading":
                return True
    
    letters = [char for char in text if char.isalpha()]
    return sum(char.isupper() for char in letters) / len(letters) >= 0.9
