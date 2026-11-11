"""
What the search tools return to the model.

A full `Document` carries every label relationship and related document, so
ten of them fill much of a model's context window. These keep what a model
needs to choose a result, quote it, and look it up again by id.
"""

import html
import re
from collections.abc import Mapping
from typing import Self

from pydantic import BaseModel

from api.mcp.filters import PRINCIPAL_LABEL_ID
from search.data_in_models import Document
from search.label import LabelSearchResult
from search.passage import Passage

DESCRIPTION_MAX_CHARS = 300
PASSAGE_TEXT_MAX_CHARS = 1500
# Enough for the model to recognise a topic; some have hundreds.
ALTERNATIVE_NAMES_MAX = 5

# Only real tags, which start with a letter or "/". Prose like "< 1.5C and
# emissions > 0" must survive.
HTML_TAG = re.compile(r"</?[a-zA-Z][^<>]*>")


class DocumentHit(BaseModel):
    id: str
    title: str
    description: str | None
    # Countries and subdivisions. World Bank regions are kept apart because
    # they're noise for most questions.
    geographies: list[str]
    regions: list[str]
    categories: list[str]
    # Not parsed, so a malformed date reaches the model rather than vanishing.
    published_date: str | None

    @classmethod
    def from_document(cls, document: Document) -> Self:
        """Trim a full document to what the model needs."""
        published_date = document.attributes.get("published_date")
        description = _plain_text(document.description)
        return cls(
            id=document.id,
            title=document.title,
            description=(
                _cut(description, DESCRIPTION_MAX_CHARS)
                if description is not None
                else None
            ),
            geographies=[
                label.value.value
                for label in document.labels
                if label.type == "geography" and label.value.type != "region"
            ],
            regions=[
                label.value.value
                for label in document.labels
                if label.type == "geography" and label.value.type == "region"
            ],
            categories=[
                label.value.value
                for label in document.labels
                if label.type == "category"
            ],
            published_date=published_date if isinstance(published_date, str) else None,
        )


class DocumentDetail(DocumentHit):
    """
    One document looked up by id.

    search_documents only returns Principals, so only a lookup needs to say
    whether this is a law's Principal or one of its versions.
    """

    is_principal: bool

    @classmethod
    def from_document(cls, document: Document) -> Self:
        """Trim a document and say whether it's a Principal."""
        hit = DocumentHit.from_document(document)
        return cls(
            **hit.model_dump(),
            is_principal=any(
                label.value.id == PRINCIPAL_LABEL_ID for label in document.labels
            ),
        )


class PassageHit(BaseModel):
    text_block_id: str
    document_id: str
    principal_id: str | None
    # The law's title, so the model can cite a passage without another call.
    # None when no document with that id was found.
    document_title: str | None
    heading: str | None
    text: str
    text_truncated: bool
    pages: list[int]

    @classmethod
    def from_passage(
        cls,
        passage: Passage,
        titles: Mapping[str, str],
        max_chars: int | None = PASSAGE_TEXT_MAX_CHARS,
    ) -> Self:
        """
        Trim a passage, cutting long text and flagging that it was cut.

        :param titles: Document titles by id, from `document_titles`.
        :param max_chars: `None` keeps the full text, for get_passage.
        """
        # Keep "<" in prose, since passages get quoted.
        text = _unescape(passage.text)
        truncated = max_chars is not None and len(text) > max_chars
        return cls(
            text_block_id=passage.text_block_id,
            document_id=passage.document_id,
            principal_id=passage.principal_id,
            document_title=titles.get(title_id(passage)),
            heading=(
                _unescape(passage.heading_text)
                if passage.heading_text is not None
                else None
            ),
            text=_cut(text, max_chars) if truncated else text,
            text_truncated=truncated,
            pages=passage.pages,
        )


def title_id(passage: Passage) -> str:
    """The id to take a passage's title from: its law's Principal, if it has one."""
    return passage.principal_id or passage.document_id


class DocumentResults(BaseModel):
    results: list[DocumentHit]
    has_more: bool


class PassageResults(BaseModel):
    results: list[PassageHit]
    has_more: bool


class PassageInContext(BaseModel):
    passage: PassageHit
    # In reading order, nearest last for `before` and nearest first for `after`.
    before: list[PassageHit]
    after: list[PassageHit]


def worth_quoting(passage: Passage) -> bool:
    """
    False for blocks that use up a result without saying anything quotable.

    Uses the layout flags set when passages are indexed: headings, page
    headers and footers, tables of contents and reference lists.
    """
    return not (
        passage.looks_like_short_heading
        or passage.is_page_header_or_footer
        or passage.looks_like_table_of_contents
        or passage.looks_like_reference_list
    )


def dedupe_passages(passages: list[Passage]) -> list[Passage]:
    """
    Drop repeated text, keeping the best ranked copy.

    The same text comes back from each version of a law, and from near
    identical documents like successive UN submissions.
    """
    seen: set[str] = set()
    unique: list[Passage] = []
    for passage in passages:
        key = " ".join(passage.text.split()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(passage)
    return unique


class TopicHit(BaseModel):
    id: str
    name: str
    alternative_names: list[str]

    @classmethod
    def from_label(cls, label: LabelSearchResult) -> Self:
        """Keep a topic's id and names, dropping its relationships."""
        return cls(
            id=label.id,
            name=label.value,
            alternative_names=label.alternative_labels[:ALTERNATIVE_NAMES_MAX],
        )


class TopicResults(BaseModel):
    results: list[TopicHit]


def _unescape(text: str) -> str:
    """Turn HTML entities like `&amp;` back into the characters they stand for."""
    # Some are escaped twice ("&amp;nbsp;"), so unescape up to 3 times.
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return text


def _plain_text(text: str | None) -> str | None:
    """Drop the HTML some descriptions are stored with, e.g. `<p>`, `<br>`."""
    if text is None:
        return None
    # `split()` also treats the non-breaking spaces from `&nbsp;` as spaces.
    return " ".join(HTML_TAG.sub(" ", _unescape(text)).split())


# A cut ends at the last of these within the limit, if one is near enough to
# it, so a quote doesn't stop mid-word or mid-clause.
SENTENCE_END = re.compile(r"[.;:!?](?=\s)|\n")
# How far back from the limit a cut may move, so it doesn't drop too much.
MIN_KEPT = 0.6


def _cut(text: str, max_chars: int | None) -> str:
    """Cut at a sentence end, or else a space, and mark the cut with "…"."""
    if max_chars is None or len(text) <= max_chars:
        return text
    window = text[:max_chars]
    earliest = int(max_chars * MIN_KEPT)
    sentence_ends = [match.end() for match in SENTENCE_END.finditer(window, earliest)]
    if sentence_ends:
        end = sentence_ends[-1]
    else:
        space = window.rfind(" ", earliest)
        end = space if space != -1 else max_chars
    return window[:end].rstrip() + " …"
