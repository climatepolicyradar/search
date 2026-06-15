"""
Threshold tuning for `ThresholdPredictor` instances.

Each predictor's continuous feature is computed once per example, then we grid-search
candidate ``(low, high)`` thresholds. Generalization is estimated with document-grouped
cross-validation (whole documents held out per fold, so chosen thresholds never peek at
the documents they're scored on), and the objective is macro-F1 over the relevant
classes 1 and 2 only (class 0 ignored).
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold

from research.document_topic_relevance.src.models import EvalExample
from research.document_topic_relevance.src.predictors import ThresholdPredictor

# Objective is computed over the "relevant" classes only; class 0 is ignored.
OBJECTIVE_LABELS: list[int] = [1, 2]


@dataclass
class ExampleFeature:
    """A precomputed feature for one example; ``feature`` is None when it has no mentions."""

    feature: float | None
    y_true: int
    group: str


@dataclass
class TuningResult:
    """Tuning outcome for one predictor."""

    name: str
    low: float
    high: float
    cv_f1_mean: float
    cv_f1_std: float
    full_f1: float


def extract_features(
    predictor: ThresholdPredictor, dataset: Sequence[EvalExample]
) -> list[ExampleFeature]:
    """Compute each example's feature once (None when the example has no mentions)."""
    out: list[ExampleFeature] = []
    for ex in dataset:
        has_mention = bool(ex.input.mentions.mentions)
        out.append(
            ExampleFeature(
                feature=predictor.feature(ex.input) if has_mention else None,
                y_true=int(ex.score),
                group=ex.input.document.original_document_id,
            )
        )
    return out


def candidate_thresholds(
    features: Sequence[ExampleFeature], n_quantiles: int
) -> list[float]:
    """Candidate thresholds = quantiles of the observed (mention-bearing) features."""
    values = [f.feature for f in features if f.feature is not None]
    if not values:
        return []
    quantiles = np.quantile(values, np.linspace(0.0, 1.0, n_quantiles))
    return sorted({float(q) for q in quantiles})


def _score(
    features: Sequence[ExampleFeature],
    low: float,
    high: float,
    higher_is_better: bool,
) -> float:
    """Macro-F1 over classes 1 & 2 at the given thresholds (no-mention examples ⇒ 0)."""
    y_true = [f.y_true for f in features]
    y_pred = [
        0
        if f.feature is None
        else ThresholdPredictor.score_from_feature(
            f.feature, low, high, higher_is_better
        )
        for f in features
    ]
    return float(
        f1_score(
            y_true,
            y_pred,
            labels=OBJECTIVE_LABELS,
            average="macro",
            zero_division=0,  # pyright: ignore[reportArgumentType]
        )
    )


def _best_thresholds(
    features: Sequence[ExampleFeature],
    candidates: Sequence[float],
    higher_is_better: bool,
) -> tuple[float, float, float]:
    """Grid-search ``(low, high)`` with ``low <= high``; return ``(low, high, score)``."""
    best_low, best_high, best_score = candidates[0], candidates[0], -1.0
    for i, low in enumerate(candidates):
        for high in candidates[i:]:
            score = _score(features, low, high, higher_is_better)
            if score > best_score:
                best_low, best_high, best_score = low, high, score
    return best_low, best_high, best_score


def tune_predictor(
    name: str,
    predictor: ThresholdPredictor,
    dataset: Sequence[EvalExample],
    *,
    folds: int,
    n_quantiles: int,
) -> TuningResult:
    """
    Tune ``(low, high)`` for one predictor with document-grouped cross-validation.

    Per fold, thresholds are selected on the training documents and scored on the
    held-out documents – the held-out fold never informs its own selection, giving an
    honest generalization estimate (``cv_f1_mean`` ± ``cv_f1_std``). The recommended
    ``(low, high)`` are then chosen by grid search on the full dataset, with ``full_f1``
    its (optimistic) full-set objective.
    """
    features = extract_features(predictor, dataset)
    candidates = candidate_thresholds(features, n_quantiles)
    if not candidates:
        return TuningResult(name, 0.0, 0.0, 0.0, 0.0, 0.0)

    higher_is_better = predictor.higher_is_better
    groups = [f.group for f in features]
    splitter = GroupKFold(n_splits=folds)
    x_dummy = np.zeros(len(features))

    fold_scores: list[float] = []
    for train_idx, test_idx in splitter.split(x_dummy, groups=groups):
        train = [features[i] for i in train_idx]
        test = [features[i] for i in test_idx]
        low, high, _ = _best_thresholds(train, candidates, higher_is_better)
        fold_scores.append(_score(test, low, high, higher_is_better))

    low, high, full_f1 = _best_thresholds(features, candidates, higher_is_better)
    return TuningResult(
        name=name,
        low=low,
        high=high,
        cv_f1_mean=float(np.mean(fold_scores)),
        cv_f1_std=float(np.std(fold_scores)),
        full_f1=full_f1,
    )


def render_tuning_report(results: Sequence[TuningResult]) -> str:
    """Markdown table, one row per predictor, sorted by CV F1(1&2) descending."""
    ordered = sorted(results, key=lambda r: r.cv_f1_mean, reverse=True)
    lines = [
        "# Threshold tuning",
        "",
        "Document-grouped cross-validation; objective = macro-F1 over classes 1 & 2.",
        "`CV F1` is the honest held-out estimate; `full-set F1` is optimistic "
        "(thresholds chosen on the same data).",
        "",
        "| Predictor | low | high | CV F1(1&2) mean | CV F1(1&2) std | full-set F1(1&2) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in ordered:
        lines.append(
            f"| {r.name} | {r.low:.4g} | {r.high:.4g} | "
            f"{r.cv_f1_mean:.3f} | {r.cv_f1_std:.3f} | {r.full_f1:.3f} |"
        )
    return "\n".join(lines) + "\n"
