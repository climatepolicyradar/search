import argparse
import csv
from pathlib import Path

from load_dataset import load_enriched_dataset_from_jsonl
from rich.console import Console
from rich.markdown import Markdown
from src.predictors import (
    DecayWeightedPredictor,
    EarliestMentionPagePredictor,
    EarliestMentionPredictor,
    FirstFractionPredictor,
    FirstNPagesDensityPredictor,
    FirstNPagesPredictor,
    MaxMentionsPerPagePredictor,
    MaxSectionDensityPredictor,
    MentionCountPredictor,
    MentionDensityPredictor,
    ThresholdPredictor,
)
from src.tuning import TuningResult, render_tuning_report, tune_predictor

console = Console()

# Each predictor with its non-threshold hyperparameters fixed at current defaults. The
# (low, high) here are placeholders – tuning searches them. Only ThresholdPredictors
# are tunable (the (low, high) family); AnyMentionIsRelevantPredictor has no thresholds.
TUNING: list[tuple[str, ThresholdPredictor]] = [
    ("mention-count", MentionCountPredictor(low=0, high=0)),
    ("mention-density", MentionDensityPredictor(low=0, high=0)),
    ("max-mentions-per-page", MaxMentionsPerPagePredictor(low=0, high=0)),
    ("max-section-density", MaxSectionDensityPredictor(low=0, high=0)),
    ("earliest-mention", EarliestMentionPredictor(low=0, high=0)),
    ("earliest-mention-page", EarliestMentionPagePredictor(low=0, high=0)),
    ("first-fraction", FirstFractionPredictor(low=0, high=0, first_fraction=0.15)),
    ("decay-weighted", DecayWeightedPredictor(low=0, high=0, decay=3.0)),
    ("first-3-pages", FirstNPagesPredictor(low=0, high=0, n_pages=3)),
    ("first-5-pages", FirstNPagesPredictor(low=0, high=0, n_pages=5)),
    ("first-10-pages", FirstNPagesPredictor(low=0, high=0, n_pages=10)),
    ("first-15-pages", FirstNPagesPredictor(low=0, high=0, n_pages=15)),
    ("first-10-pages-density", FirstNPagesDensityPredictor(low=0, high=0, n_pages=10)),
]


def main() -> None:
    """Tune (low, high) thresholds per predictor with document-grouped CV."""
    parser = argparse.ArgumentParser(
        description="Tune (low, high) thresholds per predictor"
    )
    parser.add_argument(
        "--folds", type=int, default=5, help="GroupKFold splits (grouped by document)"
    )
    parser.add_argument(
        "--quantiles",
        type=int,
        default=11,
        help="Number of candidate-threshold quantiles per predictor",
    )
    args = parser.parse_args()

    input_path = Path(__file__).parent / Path("data/dataset.jsonl")
    csv_path = Path(__file__).parent / Path("data/threshold_tuning.csv")
    md_path = Path(__file__).parent / Path("THRESHOLD_TUNING.md")

    ds = load_enriched_dataset_from_jsonl(str(input_path))
    console.log(f"📋 Loaded [bold]{len(ds)}[/bold] examples")

    # Write each predictor's result to CSV as it finishes, so nothing is lost on interrupt.
    results: list[TuningResult] = []
    with open(csv_path, "w", newline="") as cf:
        writer = csv.writer(cf)
        writer.writerow(
            ["predictor", "low", "high", "cv_f1_12_mean", "cv_f1_12_std", "full_f1_12"]
        )
        for name, predictor in TUNING:
            console.log(f"🔧 Tuning [bold]{name}[/bold]")
            result = tune_predictor(
                name, predictor, ds, folds=args.folds, n_quantiles=args.quantiles
            )
            writer.writerow(
                [
                    result.name,
                    result.low,
                    result.high,
                    result.cv_f1_mean,
                    result.cv_f1_std,
                    result.full_f1,
                ]
            )
            cf.flush()
            results.append(result)

    report = render_tuning_report(results)
    md_path.write_text(report)
    console.print(Markdown(report))
    console.log(f"💾 Wrote [bold]{md_path}[/bold] and [bold]{csv_path}[/bold]")


if __name__ == "__main__":
    main()
