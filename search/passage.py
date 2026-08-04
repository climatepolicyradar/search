import re

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
    # Persisted outputs of the `looks_like_*` heuristics below, derived at
    # materialisation time. The detectors read `text`, never these.
    short_heading: bool = Field(default=False)
    table_of_contents: bool = Field(default=False)
    reference_list: bool = Field(default=False)
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


def looks_like_reference_list(passage: Passage) -> bool:
    """
    True if the passage is a bibliography, endnote or numbered footnote block.

    Note that 'et al.' on its own is NOT a usable signal - it appears in running
    text, and per 100 words it's more frequent in the IPCC-style prose we want to
    keep (3.6) than in the reference lists we want to drop (1.7). 'doi:' is a much
    better signal, as it's rarely used outside reference lists, so it is scored
    below alongside the other locators.

    WARNING: Claude figured out the below ruleset based on seeing a sample of the data.
    It should be flexible enough for use here, but should NOT be used in production
    search.
    """
    text = passage.text
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if len(words) < 20:
        return False
    n = len(words)
    periods = text.count(".") / n * 100
    initials = len(re.findall(r"\b[A-Z]\.", text)) / n * 100
    bare_year = (
        len(
            re.findall(
                r"\(\s*(?:n\.d\.|\d{4}[a-z]?)\s*\)\s*[.,]|,\s*\d{4}[a-z]?:", text
            )
        )
        / n
        * 100
    )
    locators = (
        len(
            re.findall(r"doi:|doi\.org|https?://|Retrieved from|Available online", text)
        )
        / n
        * 100
    )
    parenthetical_cites = (
        len(re.findall(r"\([A-Z][A-Za-z.\-]+[^)]{0,60}?\d{4}[a-z]?\)", text)) / n * 100
    )
    return (
        periods / 10 + initials + 2 * bare_year + 2 * locators - 3 * parenthetical_cites
    ) >= 10


def looks_like_table_of_contents(passage: Passage) -> bool:
    """
    Returns true if the passage looks like a TOC.

    4 or more lines, at least 80% of which are short and do not terminate as sentences.

    TODO: we may be able to rely on passage types once they're in the index
    (specifically looking for list/table). See FUS-158.
    """
    lines = [line.strip() for line in passage.text.split("\n") if line.strip()]
    if len(lines) < 4:
        return False
    fragmentary = sum(
        1
        for line in lines
        if len(line.split()) <= 12 and not line.rstrip().endswith((".", "?", ";"))
    )
    return fragmentary / len(lines) >= 0.8


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
