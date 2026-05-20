import pandas as pd
from pydantic import BaseModel
from sklearn.metrics import classification_report

from research.document_topic_relevance.src.models import Score
from research.document_topic_relevance.src.predictors import DTPredictor
from search.document import Document
from search.label import Label

LABELS: list[int] = [0, 1, 2]


class ClassMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


PerClass = dict[int, ClassMetrics]


class GroupedMetrics(BaseModel):
    per_group: dict[str, PerClass]
    macro_average: PerClass


class EvaluationReport(BaseModel):
    pointwise: PerClass
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


def evaluate(
    predictor: DTPredictor,
    dataset: list[tuple[Document, Label, Score]],
) -> EvaluationReport:
    """
    Run `predictor` over dataset and compute multiclass P/R/F1 metrics.

    Reports three views:
    - `pointwise`: per-class metrics over every (document, topic) pair.
    - `by_document`: per-class metrics for each document plus a macro-average.
    - `by_topic`: per-class metrics for each topic plus a macro-average.
    """
    df = pd.DataFrame(
        [
            {
                "doc_id": doc.original_document_id,
                "topic_id": topic.id,
                "y_true": int(score),
                "y_pred": int(predictor.predict(doc, topic)),
            }
            for doc, topic, score in dataset
        ]
    )

    pointwise = _calculate_per_class_metrics(
        df["y_true"].tolist(), df["y_pred"].tolist()
    )

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

    With include_breakdowns=False, only the three headline tables are produced
    — suitable for terminal display. With True (default), the per-document and
    per-topic detail sections are appended — suitable for committing.
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
