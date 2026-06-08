from typing import Literal

from pydantic import BaseModel

from search.document import Document
from search.label import Label

Score = Literal[0, 1, 2]


class TopicMention(BaseModel):
    """One passage in which the topic is mentioned."""

    passage_index: int
    """0-based reading-order position of the passage within the document."""
    page_number: int | None = None
    section_id: int | None = None
    """Section the passage belongs to (a run of passages between section headings)."""


class TopicMentions(BaseModel):
    """Passage-level mentions of one topic within one document (from Snowflake)."""

    total_passages: int
    """Total passages in the document – the denominator for density."""
    max_page: int | None = None
    mentions: list[TopicMention] = []
    section_sizes: dict[int, int] = {}
    """Passage count of each section that contains a mention (section_id → size)."""
    passages_per_page: dict[int, int] = {}
    """Passage count of each page of the document (page_number → size)."""

    @property
    def count(self) -> int:
        """Number of passages mentioning the topic."""
        return len(self.mentions)

    @property
    def density(self) -> float:
        """Share of the document's passages that mention the topic."""
        if self.total_passages <= 0:
            return 0.0
        return self.count / self.total_passages

    @property
    def max_mentions_per_page(self) -> int:
        """Largest number of mentions occurring on any single page."""
        counts: dict[int, int] = {}
        for m in self.mentions:
            if m.page_number is None:
                continue
            counts[m.page_number] = counts.get(m.page_number, 0) + 1
        return max(counts.values(), default=0)

    @property
    def max_section_density(self) -> float:
        """
        Highest share of any single section's passages that mention the topic.

        Density measured within sections (passages between headings) rather than over
        the whole document, so a document with one section densely about the topic
        scores highly regardless of its overall length or other sections.

        Counts distinct mentioning passages per section (a passage can match the topic
        more than once), so the result is a true fraction in [0, 1].
        """
        passages_by_section: dict[int, set[int]] = {}
        for m in self.mentions:
            if m.section_id is None:
                continue
            passages_by_section.setdefault(m.section_id, set()).add(m.passage_index)
        best = 0.0
        for section_id, passages in passages_by_section.items():
            size = self.section_sizes.get(section_id, 0)
            if size > 0:
                best = max(best, len(passages) / size)
        return best

    def first_n_pages_density(self, n_pages: int) -> float:
        """
        Fraction of the first ``n_pages`` pages' passages that mention the topic.

        Like `density` but restricted to the opening of the document, so it measures
        how concentrated the early content is on the topic rather than how many early
        mentions there are (which a sparse-paged document would understate). Counts
        distinct mentioning passages, so the result is a true fraction in [0, 1].
        """
        denom = sum(c for p, c in self.passages_per_page.items() if p < n_pages)
        if denom <= 0:
            return 0.0
        early = {
            m.passage_index
            for m in self.mentions
            if m.page_number is not None and m.page_number < n_pages
        }
        return len(early) / denom

    @property
    def first_passage_index(self) -> int | None:
        """Reading-order position of the earliest mention, or None if no mentions."""
        if not self.mentions:
            return None
        return min(m.passage_index for m in self.mentions)

    @property
    def first_mention_page(self) -> int | None:
        """Earliest page on which the topic is mentioned, or None if no page info."""
        pages = [m.page_number for m in self.mentions if m.page_number is not None]
        return min(pages) if pages else None

    @property
    def earliness(self) -> float:
        """
        How early the topic first appears, in [0, 1] – earlier ⇒ higher.

        1.0 means the very first passage mentions the topic; values near 0 mean
        the first mention is at the end of the document.
        """
        first = self.first_passage_index
        if first is None or self.total_passages <= 0:
            return 0.0
        return 1.0 - (first / self.total_passages)


class PredictorInput(BaseModel):
    """Everything a predictor is allowed to see – deliberately excludes the score."""

    document: Document
    topic: Label
    mentions: TopicMentions


class EvalExample(BaseModel):
    """
    One stored/serialized dataset row.

    `score` is the ground-truth target. It lives here rather than on
    `PredictorInput` so a predictor can never read the answer it is grading against.
    """

    input: PredictorInput
    score: Score
