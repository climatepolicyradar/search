from pathlib import Path

from load_dataset import load_enriched_dataset_from_jsonl
from rich.console import Console
from rich.markdown import Markdown
from src.evaluate import EvaluationReport, evaluate, render_evaluation_report
from src.predictors import (
    AnyMentionIsRelevantPredictor,
    CombinationPredictor,
    DecayWeightedPredictor,
    DTPredictor,
    EarliestMentionPagePredictor,
    EarliestMentionPredictor,
    FirstFractionPredictor,
    FirstNPagesDensityPredictor,
    FirstNPagesPredictor,
    MaxMentionsPerPagePredictor,
    MaxSectionDensityPredictor,
    MentionCountPredictor,
    MentionDensityPredictor,
    TfIdfPredictor,
)

console = Console()

# (low, high) thresholds tuned via document-grouped cross-validation; see
# THRESHOLD_TUNING.md and tune_thresholds.py
_count = MentionCountPredictor(low=3.7, high=308.6)
_density = MentionDensityPredictor(low=0.0018735644118713008, high=0.044774726260994414)
_early_page = EarliestMentionPagePredictor(low=2, high=43.2)

PREDICTORS: dict[str, DTPredictor] = {
    "any-mention-is-relevant": AnyMentionIsRelevantPredictor(),
    "mention-count": _count,
    "mention-density": _density,
    "max-mentions-per-page": MaxMentionsPerPagePredictor(low=2, high=11.2),
    "max-section-density": MaxSectionDensityPredictor(
        low=0.09090909090909091, high=1.0
    ),
    "earliest-mention": EarliestMentionPredictor(
        low=0.38225324027916247, high=0.9854126501582999
    ),
    "earliest-mention-page": _early_page,
    "first-fraction": FirstFractionPredictor(low=1.5, high=16, first_fraction=0.15),
    "decay-weighted": DecayWeightedPredictor(
        low=1.984270124628002, high=97.3581273356797, decay=3.0
    ),
    "first-3-pages": FirstNPagesPredictor(low=0, high=1, n_pages=3),
    "first-5-pages": FirstNPagesPredictor(low=0, high=3, n_pages=5),
    "first-10-pages": FirstNPagesPredictor(low=0, high=7, n_pages=10),
    "first-15-pages": FirstNPagesPredictor(low=0, high=11, n_pages=15),
    "first-10-pages-density": FirstNPagesDensityPredictor(
        low=0, high=0.01563994722084777, n_pages=10
    ),
    # Combination predictors: combine a magnitude signal with a position
    # signal, since those families have complementary precision/recall.
    "(count or density) and early": CombinationPredictor(
        [CombinationPredictor([_count, _density], "or"), _early_page], "and"
    ),
    "density and early": CombinationPredictor([_density, _early_page], "and"),
    # TF-IDF: in-document mention signal weighted by topic rarity across the corpus.
    # (low, high) tuned via document-grouped cross-validation; see THRESHOLD_TUNING.md.
    "tfidf-density-df": TfIdfPredictor(
        low=0.0017, high=0.03091, tf_mode="density", idf_mode="df"
    ),
    "tfidf-density-cf": TfIdfPredictor(
        low=0.00969, high=0.09477, tf_mode="density", idf_mode="cf"
    ),
    "tfidf-count-df": TfIdfPredictor(
        low=3.809, high=73.6, tf_mode="count", idf_mode="df"
    ),
    "tfidf-count-cf": TfIdfPredictor(
        low=20.73, high=404.2, tf_mode="count", idf_mode="cf"
    ),
    "tfidf-lognorm-df": TfIdfPredictor(
        low=0.2851, high=3.514, tf_mode="lognorm", idf_mode="df"
    ),
}


def main() -> None:
    """Evaluate predictors against the ground truth dataset"""

    input_path = Path(__file__).parent / Path("data/dataset.jsonl")
    output_path = Path(__file__).parent / Path("PREDICTOR_METRICS.md")

    ds = load_enriched_dataset_from_jsonl(str(input_path))
    n_docs = len({ex.input.document.original_document_id for ex in ds})
    n_topics = len({ex.input.topic.id for ex in ds})
    console.log(
        f"📋 Loaded [bold]{len(ds)}[/bold] examples "
        f"over {n_docs} documents and {n_topics} topics"
    )

    reports: dict[str, EvaluationReport] = {}
    for name, predictor in PREDICTORS.items():
        console.log(f"🤖 Running [bold]{name}[/bold]")
        reports[name] = evaluate(predictor, ds)

    console.print(
        Markdown(
            render_evaluation_report(
                reports,
                dataset_path=str(input_path),
                n_examples=len(ds),
                n_docs=n_docs,
                n_topics=n_topics,
                include_breakdowns=False,
            )
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_evaluation_report(
            reports,
            dataset_path=str(input_path),
            n_examples=len(ds),
            n_docs=n_docs,
            n_topics=n_topics,
            include_breakdowns=True,
        )
    )
    console.log(f"💾 Wrote report to [bold]{output_path}[/bold]")


if __name__ == "__main__":
    main()
