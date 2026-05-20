from pathlib import Path

from load_dataset import load_enriched_dataset_from_jsonl
from rich.console import Console
from rich.markdown import Markdown
from src.evaluate import EvaluationReport, evaluate, render_evaluation_report
from src.predictors import AnyMentionIsRelevantPredictor, DTPredictor

console = Console()

PREDICTORS: dict[str, DTPredictor] = {
    "any-mention-is-relevant": AnyMentionIsRelevantPredictor(),
}


def main() -> None:
    """Evaluate predictors against the ground truth dataset"""

    input_path = Path(__file__).parent / Path("data/dataset.jsonl")
    output_path = Path(__file__).parent / Path("PREDICTOR_METRICS.md")

    ds = load_enriched_dataset_from_jsonl(str(input_path))
    n_docs = len({d.original_document_id for d, _, _ in ds})
    n_topics = len({t.id for _, t, _ in ds})
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
