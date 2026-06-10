from collections import defaultdict

import pandas as pd
from pydantic import BaseModel
from sklearn.metrics import (
    classification_report,
    ndcg_score,
    precision_recall_fscore_support,
)

from research.document_topic_relevance.src.models import EvalExample
from research.document_topic_relevance.src.predictors import DTPredictor

LABELS: list[int] = [0, 1, 2]
RELEVANT_LABELS: list[int] = [1, 2]


class ClassMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


PerClass = dict[int, ClassMetrics]


class BinaryMetrics(BaseModel):
    """Detection metrics for the positive class = {1, 2} collapsed against 0."""

    precision: float
    recall: float
    f1: float
    positives: int


class GroupedMetrics(BaseModel):
    per_group: dict[str, PerClass]
    macro_average: PerClass


class NdcgMetrics(BaseModel):
    """
    Ranking quality of the predictor's continuous score against graded labels.

    `per_document_macro` ranks each document's *topics* and averages – the
    "most relevant topics for a document" view, and the one a per-topic weighting
    like IDF can improve (IDF varies across the topics within a document, so it
    reweights their order). `global_pooled` ranks *all* (document, topic) pairs
    together. `per_topic_macro` ranks each topic's *documents* and averages; it is
    invariant to any per-topic constant, so IDF cannot change it (kept as a
    feature-quality cross-check).
    """

    per_document_macro: float
    global_pooled: float
    per_topic_macro: float
    n_documents_scored: int
    n_topics_scored: int


class EvaluationReport(BaseModel):
    pointwise: PerClass
    binary: BinaryMetrics
    ndcg: NdcgMetrics
    by_document: GroupedMetrics
    by_topic: GroupedMetrics


def _calculate_per_class_metrics(y_true: list[int], y_pred: list[int]) -> PerClass:
    raw: dict = classification_report(  # pyright: ignore[reportAssignmentType]
        y_true,
        y_pred,
        labels=LABELS,
        output_dict=True,
        zero_division=0,  # pyright: ignore[reportArgumentType]
    )
    return {
        cls: ClassMetrics(
            precision=raw[str(cls)]["precision"],
            recall=raw[str(cls)]["recall"],
            f1=raw[str(cls)]["f1-score"],
            support=int(raw[str(cls)]["support"]),
        )
        for cls in LABELS
    }


def _macro(groups: dict[str, PerClass]) -> PerClass:
    """
    Macro-average per-class metrics across groups.

    Skips groups where the class has zero support, i.e. the class doesn't appear in the
    group's ground truth, so per-class recall is undefined for that group.
    """
    out: PerClass = {}
    for c in LABELS:
        contributing = [g[c] for g in groups.values() if g[c].support > 0]
        n = len(contributing)
        if n == 0:
            out[c] = ClassMetrics(precision=0.0, recall=0.0, f1=0.0, support=0)
            continue
        out[c] = ClassMetrics(
            precision=sum(m.precision for m in contributing) / n,
            recall=sum(m.recall for m in contributing) / n,
            f1=sum(m.f1 for m in contributing) / n,
            support=sum(m.support for m in contributing),
        )
    return out


def _binary_metrics(y_true: list[int], y_pred: list[int]) -> BinaryMetrics:
    """Detection metrics treating classes 1 & 2 as one positive class vs 0."""
    yt = [1 if v in RELEVANT_LABELS else 0 for v in y_true]
    yp = [1 if v in RELEVANT_LABELS else 0 for v in y_pred]
    precision, recall, f1, _ = precision_recall_fscore_support(
        yt,
        yp,
        average="binary",
        pos_label=1,
        zero_division=0,  # pyright: ignore[reportArgumentType]
    )
    return BinaryMetrics(
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        positives=sum(yt),
    )


def _ranking_scores(predictor: DTPredictor, dataset: list[EvalExample]) -> list[float]:
    """
    A continuous "higher ⇒ more relevant" score per example, for ranking.

    For a `ThresholdPredictor` the raw feature is used (negated when smaller means
    more relevant), mirroring the threshold-tuning convention; pairs with no mentions
    have no meaningful feature and are floored below every real score so they rank
    last. Non-threshold predictors fall back to their `{0,1,2}` prediction.

    Detection is by duck typing (a `feature` method + `higher_is_better` flag) rather
    than `isinstance`: scripts import predictors as `src.predictors` while this module
    imports the fully-qualified path, so the classes are distinct objects at runtime.
    """
    is_threshold = hasattr(predictor, "feature") and hasattr(
        predictor, "higher_is_better"
    )
    raw: list[float | None] = []
    for ex in dataset:
        x = ex.input
        if is_threshold:
            if not x.mentions.mentions:
                raw.append(None)
            else:
                feature = predictor.feature(x)  # pyright: ignore[reportAttributeAccessIssue]
                higher_is_better = predictor.higher_is_better  # pyright: ignore[reportAttributeAccessIssue]
                raw.append(feature if higher_is_better else -feature)
        else:
            raw.append(float(predictor.predict(x)))
    finite = [r for r in raw if r is not None]
    floor = (min(finite) - 1.0) if finite else 0.0
    return [floor if r is None else r for r in raw]


def _ndcg_metrics(predictor: DTPredictor, dataset: list[EvalExample]) -> NdcgMetrics:
    """Per-document, global-pooled and per-topic NDCG over the ranking score."""
    y_true = [int(ex.score) for ex in dataset]
    scores = _ranking_scores(predictor, dataset)

    def _ndcg(true: list[int], score: list[float]) -> float | None:
        # NDCG needs ≥2 items and some non-zero relevance to be well defined.
        if len(true) < 2 or not any(true):
            return None
        return float(ndcg_score([true], [score]))

    def _grouped_macro(key) -> tuple[float, int]:
        """Macro-average NDCG over groups keyed by `key`, skipping degenerate ones."""
        groups: dict[str, tuple[list[int], list[float]]] = defaultdict(lambda: ([], []))
        for ex, yt, sc in zip(dataset, y_true, scores):
            trues, scs = groups[key(ex)]
            trues.append(yt)
            scs.append(sc)
        scored = [
            ndcg
            for trues, scs in groups.values()
            if (ndcg := _ndcg(trues, scs)) is not None
        ]
        return (sum(scored) / len(scored) if scored else 0.0), len(scored)

    global_pooled = _ndcg(y_true, scores) or 0.0
    per_document_macro, n_documents = _grouped_macro(
        lambda ex: ex.input.document.original_document_id
    )
    per_topic_macro, n_topics = _grouped_macro(lambda ex: ex.input.topic.id)

    return NdcgMetrics(
        per_document_macro=per_document_macro,
        global_pooled=global_pooled,
        per_topic_macro=per_topic_macro,
        n_documents_scored=n_documents,
        n_topics_scored=n_topics,
    )


def evaluate(
    predictor: DTPredictor,
    dataset: list[EvalExample],
) -> EvaluationReport:
    """
    Run `predictor` over dataset and compute multiclass P/R/F1 metrics.

    Reports four views:
    - `pointwise`: per-class metrics over every (document, topic) pair.
    - `binary`: detection metrics with classes 1 & 2 collapsed into one positive
      class against 0.
    - `by_document`: per-class metrics for each document plus a macro-average.
    - `by_topic`: per-class metrics for each topic plus a macro-average.
    """
    df = pd.DataFrame(
        [
            {
                "doc_id": ex.input.document.original_document_id,
                "topic_id": ex.input.topic.id,
                "y_true": int(ex.score),
                "y_pred": int(predictor.predict(ex.input)),
            }
            for ex in dataset
        ]
    )

    pointwise = _calculate_per_class_metrics(
        df["y_true"].tolist(), df["y_pred"].tolist()
    )
    binary = _binary_metrics(df["y_true"].tolist(), df["y_pred"].tolist())
    ndcg = _ndcg_metrics(predictor, dataset)

    metrics_by_doc = {
        str(doc_id): _calculate_per_class_metrics(
            g["y_true"].tolist(), g["y_pred"].tolist()
        )
        for doc_id, g in df.groupby("doc_id")
    }
    metrics_by_topic = {
        str(topic_id): _calculate_per_class_metrics(
            g["y_true"].tolist(), g["y_pred"].tolist()
        )
        for topic_id, g in df.groupby("topic_id")
    }

    return EvaluationReport(
        pointwise=pointwise,
        binary=binary,
        ndcg=ndcg,
        by_document=GroupedMetrics(
            per_group=metrics_by_doc, macro_average=_macro(metrics_by_doc)
        ),
        by_topic=GroupedMetrics(
            per_group=metrics_by_topic, macro_average=_macro(metrics_by_topic)
        ),
    )


def _md_table(reports: dict[str, PerClass]) -> str:
    lines = [
        "| Predictor | Class | Precision | Recall | F1 | Support |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for predictor_name, per_class in reports.items():
        for cls in LABELS:
            m = per_class[cls]
            lines.append(
                f"| {predictor_name} | {cls} | {m.precision:.3f} | "
                f"{m.recall:.3f} | {m.f1:.3f} | {m.support} |"
            )
    return "\n".join(lines)


def _f1_relevant(per_class: PerClass) -> float:
    """Arithmetic mean of F1 over the relevant classes (RELEVANT_LABELS) only."""
    return sum(per_class[c].f1 for c in RELEVANT_LABELS) / len(RELEVANT_LABELS)


def _summary_table(reports: dict[str, PerClass]) -> str:
    """
    Render a leaderboard with one row per predictor

    Predictions are sorted by F1 on classes 1 & 2 descending.

    Precision/recall/F1 are arithmetic means across the classes in LABELS; support
    is the total across those classes. `F1 (cls 1&2)` is the arithmetic mean of F1
    over only the classes in RELEVANT_LABELS, and is the sort key. The per-class
    precision/recall columns report classes 1 and 2 individually.
    """
    ordered = sorted(reports.items(), key=lambda kv: _f1_relevant(kv[1]), reverse=True)

    n = len(LABELS)
    lines = [
        "| Predictor | Precision | Recall | F1 | F1 (cls 1&2) "
        "| P (cls1) | R (cls1) | P (cls2) | R (cls2) | Support |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for predictor_name, per_class in ordered:
        precision = sum(per_class[c].precision for c in LABELS) / n
        recall = sum(per_class[c].recall for c in LABELS) / n
        f1 = sum(per_class[c].f1 for c in LABELS) / n
        support = sum(per_class[c].support for c in LABELS)
        lines.append(
            f"| {predictor_name} | {precision:.3f} | {recall:.3f} | {f1:.3f} "
            f"| {_f1_relevant(per_class):.3f} "
            f"| {per_class[1].precision:.3f} | {per_class[1].recall:.3f} "
            f"| {per_class[2].precision:.3f} | {per_class[2].recall:.3f} "
            f"| {support} |"
        )
    return "\n".join(lines)


def _binary_table(reports: dict[str, BinaryMetrics]) -> str:
    """Leaderboard for the binary detection task, sorted by F1 descending."""
    ordered = sorted(reports.items(), key=lambda kv: kv[1].f1, reverse=True)
    lines = [
        "| Predictor | Precision | Recall | F1 | Positives |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for predictor_name, m in ordered:
        lines.append(
            f"| {predictor_name} | {m.precision:.3f} | {m.recall:.3f} "
            f"| {m.f1:.3f} | {m.positives} |"
        )
    return "\n".join(lines)


def _ndcg_table(reports: dict[str, NdcgMetrics]) -> str:
    """Ranking leaderboard, sorted by per-document NDCG (top topics per document)."""
    ordered = sorted(
        reports.items(), key=lambda kv: kv[1].per_document_macro, reverse=True
    )
    lines = [
        "| Predictor | NDCG (by document) | NDCG (global pooled) | "
        "NDCG (by topic) | Docs scored | Topics scored |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for predictor_name, m in ordered:
        lines.append(
            f"| {predictor_name} | {m.per_document_macro:.3f} | {m.global_pooled:.3f} "
            f"| {m.per_topic_macro:.3f} | {m.n_documents_scored} | {m.n_topics_scored} |"
        )
    return "\n".join(lines)


def render_evaluation_report(
    reports: dict[str, EvaluationReport],
    *,
    dataset_path: str | None = None,
    n_examples: int | None = None,
    n_docs: int | None = None,
    n_topics: int | None = None,
    include_breakdowns: bool = True,
) -> str:
    """
    Render one markdown report comparing multiple predictors.

    Opens with three leaderboards (one row per predictor, sorted by F1 on classes
    1 & 2): pointwise over all pairs, macro-averaged by document, and macro-averaged
    by topic. With include_breakdowns=False only the headline leaderboards and tables
    are produced — suitable for terminal display. With True (default), the per-document
    and per-topic detail sections are appended — suitable for committing.
    """
    sections: list[str] = [
        "# Document-topic relevance evaluation",
        "",
        f"- Dataset: `{dataset_path}`" if dataset_path is not None else "",
        f"- Examples: {n_examples} ({n_docs} documents × {n_topics} topics)"
        if n_examples is not None
        else "",
        f"- Predictors: {', '.join(reports)}",
        "",
        "## Summary — pointwise over all pairs (sorted by F1 on classes 1 & 2)",
        "",
        _summary_table({name: r.pointwise for name, r in reports.items()}),
        "",
        "## Summary — macro-averaged by document (sorted by F1 on classes 1 & 2)",
        "",
        _summary_table(
            {name: r.by_document.macro_average for name, r in reports.items()}
        ),
        "",
        "## Summary — macro-averaged by topic (sorted by F1 on classes 1 & 2)",
        "",
        _summary_table({name: r.by_topic.macro_average for name, r in reports.items()}),
        "",
        "## Summary — binary: relevant (1 or 2) vs not (0), sorted by F1",
        "",
        _binary_table({name: r.binary for name, r in reports.items()}),
        "",
        "## Summary — ranking quality (NDCG), sorted by NDCG by document",
        "",
        "Ranks pairs by the predictor's continuous score against graded {0,1,2} "
        "labels. *By document* ranks each document's topics — the "
        '"most relevant topics for a document" view, where IDF (which varies '
        "across a document's topics) can reorder them. *Global pooled* ranks all "
        "pairs together. *By topic* ranks documents within a topic and is invariant "
        "to per-topic constants, so TF and TF×IDF score identically there.",
        "",
        _ndcg_table({name: r.ndcg for name, r in reports.items()}),
        "",
        "## Pointwise (over all pairs)",
        "",
        _md_table({name: r.pointwise for name, r in reports.items()}),
        "",
        "## Macro average across documents (skipping zero-support groups per class)",
        "",
        _md_table({name: r.by_document.macro_average for name, r in reports.items()}),
        "",
        "## Macro-average across topics (skipping zero-support groups per class)",
        "",
        _md_table({name: r.by_topic.macro_average for name, r in reports.items()}),
        "",
    ]

    if include_breakdowns:
        sections += ["## Per-document breakdowns", ""]
        doc_ids = sorted(
            {did for r in reports.values() for did in r.by_document.per_group}
        )
        for doc_id in doc_ids:
            sections.append(f"### `{doc_id}`")
            sections.append("")
            sections.append(
                _md_table(
                    {
                        name: r.by_document.per_group[doc_id]
                        for name, r in reports.items()
                        if doc_id in r.by_document.per_group
                    }
                )
            )
            sections.append("")

        sections += ["## Per-topic breakdowns", ""]
        topic_ids = sorted(
            {tid for r in reports.values() for tid in r.by_topic.per_group}
        )
        for topic_id in topic_ids:
            sections.append(f"### `{topic_id}`")
            sections.append("")
            sections.append(
                _md_table(
                    {
                        name: r.by_topic.per_group[topic_id]
                        for name, r in reports.items()
                        if topic_id in r.by_topic.per_group
                    }
                )
            )
            sections.append("")

    return "\n".join(sections) + "\n"
