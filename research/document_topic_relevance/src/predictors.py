import itertools
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Literal

from research.document_topic_relevance.src.models import PredictorInput, Score


class DTPredictor(ABC):
    """
    Predictor for bidirectional relevance between a topic and a document

    Encodes the assumption that if a topic is not mentioned in a document, it cannot
    be relevant – so it has a score of 0.
    """

    def predict(self, x: PredictorInput) -> Score:
        """Predict document-topic relevance"""

        if not x.mentions.mentions:
            return 0

        return self._predict(x)

    @abstractmethod
    def _predict(self, x: PredictorInput) -> Score:
        raise NotImplementedError()


class ThresholdPredictor(DTPredictor, ABC):
    """
    Compute a continuous feature, then map it to a {0, 1, 2} score via two thresholds.

    By default higher feature values mean more relevant: `>= high` scores 2, `>= low`
    scores 1, otherwise 0. Subclasses where *smaller* is more relevant (e.g. a page
    number) set `higher_is_better = False`, which inverts the mapping so `low`/`high`
    are upper cutoffs: `<= low` scores 2, `<= high` scores 1, otherwise 0. Either way
    `low <= high`. Subclasses only need to implement `_feature`.
    """

    higher_is_better: bool = True

    def __init__(self, low: float, high: float) -> None:
        if low > high:
            raise ValueError(f"low ({low}) must be <= high ({high})")
        self.low: float = low
        self.high: float = high

    @abstractmethod
    def _feature(self, x: PredictorInput) -> float:
        raise NotImplementedError()

    def feature(self, x: PredictorInput) -> float:
        """Public accessor for the continuous feature (used by threshold tuning)."""
        return self._feature(x)

    @staticmethod
    def score_from_feature(
        feature: float, low: float, high: float, higher_is_better: bool = True
    ) -> Score:
        """
        Map a feature value to a {0, 1, 2} score given the two thresholds.

        With `higher_is_better` (default): `>= high` → 2, `>= low` → 1, else 0.
        Otherwise (smaller is better): `<= low` → 2, `<= high` → 1, else 0.
        """
        if higher_is_better:
            if feature >= high:
                return 2
            if feature >= low:
                return 1
            return 0
        if feature <= low:
            return 2
        if feature <= high:
            return 1
        return 0

    def _predict(self, x: PredictorInput) -> Score:
        return self.score_from_feature(
            self._feature(x), self.low, self.high, self.higher_is_better
        )


class AnyMentionIsRelevantPredictor(DTPredictor):
    """All mentions of a topic in a document result in a score of 2."""

    def _predict(self, x: PredictorInput) -> Score:  # noqa: ARG002
        return 2


class CombinationPredictor(DTPredictor):
    """
    Combine sub-predictors with fuzzy AND/OR over their ordinal {0, 1, 2} scores.

    `"and"` takes the min of the sub-scores (relevant only as far as the weakest signal
    agrees); `"or"` takes the max (relevant as far as the strongest signal says).
    Combinations nest, so e.g. "(count OR density) AND early" is
    ``CombinationPredictor([CombinationPredictor([count, density], "or"), early], "and")``.
    """

    def __init__(
        self, predictors: Sequence[DTPredictor], mode: Literal["and", "or"]
    ) -> None:
        if not predictors:
            raise ValueError("CombinationPredictor needs at least one sub-predictor")
        self.predictors = list(predictors)
        self.mode = mode

    def _predict(self, x: PredictorInput) -> Score:
        scores: list[Score] = [p.predict(x) for p in self.predictors]
        return min(scores) if self.mode == "and" else max(scores)


class MentionCountPredictor(ThresholdPredictor):
    """Score from the raw number of passages mentioning the topic."""

    def _feature(self, x: PredictorInput) -> float:
        return x.mentions.count


class MentionDensityPredictor(ThresholdPredictor):
    """Score from the share of the document's passages that mention the topic."""

    def _feature(self, x: PredictorInput) -> float:
        return x.mentions.density


class MaxMentionsPerPagePredictor(ThresholdPredictor):
    """
    Score from the peak number of mentions on any single page.

    A density measure that doesn't penalise long documents (per Anne's note): a
    document with a page densely about the topic scores highly regardless of length.
    """

    def _feature(self, x: PredictorInput) -> float:
        return x.mentions.max_mentions_per_page


class MaxSectionDensityPredictor(ThresholdPredictor):
    """
    Score from the peak mention density within any single section.

    Density measured per section (passages between headings) rather than over the whole
    document – Anne's "ideal" length-normalised measure. A document with one section
    densely about the topic scores highly regardless of overall length, and topically
    mixed documents aren't buried the way whole-document density would bury them.
    """

    def _feature(self, x: PredictorInput) -> float:
        return x.mentions.max_section_density


class EarliestMentionPredictor(ThresholdPredictor):
    """
    Score from how early the topic first appears – earlier ⇒ more relevant.

    The feature is in [0, 1], where 1.0 means the first passage mentions the topic.
    """

    def _feature(self, x: PredictorInput) -> float:
        return x.mentions.earliness


class EarliestMentionPagePredictor(ThresholdPredictor):
    """
    Score from the page of the topic's earliest mention – earlier page ⇒ more relevant.

    Like `EarliestMentionPredictor` but on absolute (0-indexed) page numbers rather than
    the fraction of the document, so `low`/`high` are page-number cutoffs (`low <= high`):
    first mention on page `<= low` scores 2, `<= high` scores 1, else 0.
    """

    higher_is_better = False

    def _feature(self, x: PredictorInput) -> float:
        page = x.mentions.first_mention_page
        if page is not None:
            return float(page)
        # No page info on any mention: treat as very late so it cannot look early.
        return float(x.mentions.max_page if x.mentions.max_page is not None else 10**6)


class FirstNPagesPredictor(ThresholdPredictor):
    """
    Score from the number of mentions within the first ``n_pages`` pages.

    A topic appearing early in the document is more likely to be central to it.
    Page numbers are 0-indexed, so the first N pages are those with
    ``page_number < n_pages``. Mentions with no page number are ignored.
    """

    def __init__(self, low: float, high: float, n_pages: int = 3) -> None:
        super().__init__(low=low, high=high)
        self.n_pages: int = n_pages

    def _feature(self, x: PredictorInput) -> float:
        return sum(
            1
            for m in x.mentions.mentions
            if m.page_number is not None and m.page_number < self.n_pages
        )


class FirstNPagesDensityPredictor(ThresholdPredictor):
    """
    Score from the mention density within the first ``n_pages`` pages.

    Like `FirstNPagesPredictor` but normalised by how many passages those early pages
    contain, so it measures how concentrated the opening is on the topic rather than
    the raw count (which a sparse-paged document would understate).
    """

    def __init__(self, low: float, high: float, n_pages: int = 10) -> None:
        super().__init__(low=low, high=high)
        self.n_pages: int = n_pages

    def _feature(self, x: PredictorInput) -> float:
        return x.mentions.first_n_pages_density(self.n_pages)


class FirstFractionPredictor(ThresholdPredictor):
    """
    Score from the number of mentions within the first ``first_fraction`` of the doc.

    Position is measured by passage reading order, so the cutoff is
    ``first_fraction * total_passages``. A topic concentrated near the start is more
    likely to be central. ``first_fraction`` is in (0, 1] – e.g. 0.15 = first 15%.
    """

    def __init__(self, low: float, high: float, first_fraction: float = 0.15) -> None:
        super().__init__(low=low, high=high)
        if not 0 < first_fraction <= 1:
            raise ValueError(f"first_fraction must be in (0, 1], got {first_fraction}")
        self.first_fraction: float = first_fraction

    def _feature(self, x: PredictorInput) -> float:
        cutoff = self.first_fraction * x.mentions.total_passages
        return sum(1 for m in x.mentions.mentions if m.passage_index < cutoff)


class DecayWeightedPredictor(ThresholdPredictor):
    """
    Score from mentions weighted by position, with earlier mentions weighting more.

    Each mention at relative position ``p = passage_index / total_passages`` (0 at the
    start, ~1 at the end) contributes ``exp(-decay * p)``. The feature is the sum of
    these weights. ``decay = 0`` recovers a plain mention count; larger ``decay``
    concentrates credit on early mentions.
    """

    def __init__(self, low: float, high: float, decay: float = 3.0) -> None:
        super().__init__(low=low, high=high)
        if decay < 0:
            raise ValueError(f"decay must be >= 0, got {decay}")
        self.decay: float = decay

    def _feature(self, x: PredictorInput) -> float:
        total = x.mentions.total_passages
        if total <= 0:
            return 0.0
        return sum(
            math.exp(-self.decay * (m.passage_index / total))
            for m in x.mentions.mentions
        )


def sweep(
    prefix: str,
    predictor_cls: type[ThresholdPredictor],
    **param_grid: Sequence[float],
) -> dict[str, ThresholdPredictor]:
    """
    Build a registry of predictor instances over a grid of hyperparameter values.

    Each keyword maps a hyperparameter name to the list of values to try; one instance
    is created per point in the cartesian product. Only hyperparameters with more than
    one value appear in the generated key, keeping names readable:

        sweep("first-pages", FirstNPagesPredictor, low=[1], high=[3], n_pages=[3, 10])
        # -> {"first-pages[n_pages=3]": ..., "first-pages[n_pages=10]": ...}
    """
    names = list(param_grid)
    varying = [n for n in names if len(param_grid[n]) > 1]
    out: dict[str, ThresholdPredictor] = {}
    for combo in itertools.product(*(param_grid[n] for n in names)):
        kwargs = dict(zip(names, combo))
        suffix = ",".join(f"{n}={kwargs[n]}" for n in varying)
        key = f"{prefix}[{suffix}]" if suffix else prefix
        out[key] = predictor_cls(**kwargs)
    return out
