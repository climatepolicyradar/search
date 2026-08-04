import re
from collections.abc import Callable

from pydantic import BaseModel, Field, computed_field


class Coordinate(BaseModel):
    """A single x/y point in a bounding-box polygon."""

    x: float = Field(default=0.0)
    y: float = Field(default=0.0)


class BoundingBox(BaseModel):
    """A polygon (list of coordinate points) bounding part of a passage on a page."""

    coordinates: list[Coordinate] = Field(default_factory=list)


class PageWithBoundingBoxes(BaseModel):
    """A page number paired with the bounding boxes locating a passage on it."""

    number: int = Field(default=0)
    bounding_boxes: list[BoundingBox] = Field(default_factory=list)


class Concept(BaseModel):
    """A concept/topic mentioned within a passage, with its mention count."""

    id: str = Field(default="")
    type: str = Field(default="")
    value: str = Field(default="")
    count: int = Field(default=0)


class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    idx: int = Field(default=0)
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    page_number: int = Field(default=0)
    pages: list[int] = Field(default_factory=list)
    pages_with_bounding_boxes: list[PageWithBoundingBoxes] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    heading_id: str | None = Field(default=None)
    heading_text: str | None = Field(default=None)
    document_id: str = Field(default="")
    principal_id: str | None = Field(default=None)
    # TODO: this is Vespa's own on-the-fly tokenization of `text` (via
    # debug-summary), NOT the same as the Snowflake model's `tokens` column
    # (Python-side tokenization fed INTO Vespa). Will likely remove this field
    # in the future - just here for now to expose for discovery for the UI
    # project.
    tokens: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        """A canonical identifier for the passage."""
        return self.text_block_id


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
_MIN_WORDS = 20


def looks_like_reference_list(passage: Passage) -> bool:
    """
    True if the passage is a bibliography, endnote or numbered footnote block.

    Reads as: it is a reference list if it is long enough to judge, does not read
    as prose, is not a contact block, and at least two of four named citation
    signals hold.

    Requiring *two* signals is what does the work. Any one of them alone fires on
    far too much - a URL in a footnote, a date in a table, an initial in a
    signature block - but a passage carrying two of author initials, citation
    years, source locators and period density is a citation list and almost
    nothing else. Dropping to one signal takes precision from 1.00 to 0.86;
    demanding three takes recall from 0.98 to 0.86.

    Calendar dates are stripped before counting: the ', 2024.' of 'December 31,
    2024.' is otherwise indistinguishable from a citation year.

    Unlike `looks_like_table_of_contents`, there is no positional condition here.
    Reference lists sit at a median 0.62 of the way through their document against
    0.55 for everything else - the distributions are the same, because numbered
    footnote citations appear on every page rather than only at the end.

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
      (3.6) than in the reference lists we want to drop (1.7).

    Dropping publication furniture has a known cost: a block of legal footnotes
    carrying URLs, 'Id.' and 'supra' scores just under all four thresholds and so
    fires no signal at all.

    WARNING: Claude figured out the below ruleset based on a labelled sample of
    the data. It should be flexible enough for use, but should be used with caution in
    production applications.
    """
    text = _CALENDAR_DATE.sub(" ", passage.text)
    words = _WORD.findall(text)
    if len(words) < _MIN_WORDS:
        return False

    def per_100_words(pattern: re.Pattern) -> float:
        return len(pattern.findall(text)) / len(words) * 100

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


def looks_like_table_of_contents(passage: Passage) -> bool:
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
    does not read `text`. It is skipped when `pages` is empty.

    Collapsed contents listings (a whole TOC on one line, no newlines) are not
    detected: they are indistinguishable here from prose carrying a 'Table of
    Contents' running-header artefact.

    WARNING: Claude figured out the below ruleset from a labelled sample of the
    data. It should be flexible enough for use here, but should be used with caution.

    TODO: we may be able to rely on passage types once they're in the index
    (specifically looking for list/table). See FUS-158.
    """
    if passage.pages and min(passage.pages) > _FRONT_MATTER_MAX_PAGE:
        return False

    text = passage.text
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
    page_numbers: list[int] = []
    titles: set[str] = set()
    for line in entries:
        match = _TRAILING_LOCATOR.search(line)
        if match and (page := _folio(match.group(1))):
            page_numbers.append(page)
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
        len(page_numbers) / len(entries) >= _PAGE_NUMBER_SHARE
        and len(titles) / len(page_numbers) >= _DISTINCT_TITLE_SHARE
        and _never_goes_backwards(page_numbers)
    )

    return (
        names_itself_an_index
        or is_hierarchically_numbered
        or names_standard_sections
        or is_flatly_numbered
        or entries_end_in_climbing_page_numbers
    )


def looks_like_short_heading(passage: Passage) -> bool:
    """
    True if the passage is a short ALLCAPS figure title or section heading.

    Fewer than 12 words, and at least 90% of the cased characters are upper case.
    The parser's `sectionHeading` type would be a better signal - see the note in
    `looks_like_table_of_contents` for when we can switch to it.

    TODO: this should be replaced with using the passage type once it's in the index
    """
    text = passage.text
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if not words or len(words) >= 12:
        return False
    letters = [char for char in text if char.isalpha()]

    return sum(char.isupper() for char in letters) / len(letters) >= 0.9
