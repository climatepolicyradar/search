"""
Score the passage type detectors against the hand-labelled validation sets.

    uv run python research/passage_detectors/evaluate.py

See README.md for what each stratum is and, importantly, which ones must not be
used to compare two candidate rules.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.table import Table
from sklearn.metrics import precision_recall_fscore_support

# The detectors are the feeder's - it is what production runs, so scoring
# anything else would be scoring a copy. `passages_derived_data` is
# deliberately stdlib-only, so importing it needs no more than this: the
# feeder ships no package, its modules are flat files on PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vespa-feeder"))

from passages_derived_data import (  # noqa: E402
    looks_like_reference_list,
    looks_like_table_of_contents,
)

DATA_DIR = Path(__file__).parent / "data"
# `looks_like_table_of_contents` reads page numbers, `looks_like_reference_list`
# does not - both are adapted to this shape so `score` stays uniform.
Detector = Callable[[str, list[int]], bool]
# The slice the README quotes its baselines on, because it excludes the rows added
# after the detectors were developed and so is comparable with their history.
BASELINE_SLICE = "original strata only"

console = Console()


def load_dataset(name: str) -> list[dict]:
    lines = (DATA_DIR / name).read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def score(
    rows: list[dict], detector: Detector, *, use_pages: bool
) -> tuple[float, float, float, int, int]:
    """Precision, recall, F1 and the raw error counts for one slice."""
    truth, predicted = [], []
    for row in rows:
        pages = [row["min_page"]] if use_pages and row["min_page"] is not None else []
        truth.append(row["label"])
        predicted.append(int(detector(row["content"], pages)))
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth,
        predicted,
        average="binary",
        zero_division=0,  # pyright: ignore[reportArgumentType]
    )
    false_pos = sum(1 for t, p in zip(truth, predicted) if p and not t)
    false_neg = sum(1 for t, p in zip(truth, predicted) if t and not p)
    return precision, recall, f1, false_pos, false_neg  # pyright: ignore[reportReturnType]


def report(name: str, rows: list[dict], detector: Detector, *, use_pages: bool) -> None:
    slices: list[tuple[str, list[dict]]] = [
        ("all rows", rows),
        ("excluding ambiguous", [r for r in rows if not r["ambiguous"]]),
        (BASELINE_SLICE, [r for r in rows if r["stratum"] != "fresh_disagreement"]),
        (
            "fresh_disagreement (out of sample)",
            [r for r in rows if r["stratum"] == "fresh_disagreement"],
        ),
    ]

    # Printed outside the table: as a title rich would wrap it to the table's
    # width, which breaks these long detector names mid-phrase.
    console.print(f"[bold]{name}[/bold] — {len(rows)} rows")

    table = Table()
    table.add_column("slice", style="cyan")
    table.add_column("P", justify="right")
    table.add_column("R", justify="right")
    table.add_column("F1", justify="right")
    table.add_column("fp", justify="right", style="red")
    table.add_column("fn", justify="right", style="yellow")
    for label, subset in slices:
        if not subset:
            continue
        precision, recall, f1, false_pos, false_neg = score(
            subset, detector, use_pages=use_pages
        )
        table.add_row(
            label,
            f"{precision:.3f}",
            f"{recall:.3f}",
            f"{f1:.3f}",
            str(false_pos),
            str(false_neg),
            style="bold" if label == BASELINE_SLICE else None,
        )
    console.print(table)

    strata = Table(title="by stratum", title_justify="left", box=None, pad_edge=False)
    strata.add_column("stratum", style="cyan")
    strata.add_column("n", justify="right")
    strata.add_column("positives", justify="right")
    strata.add_column("fp", justify="right", style="red")
    strata.add_column("fn", justify="right", style="yellow")
    for stratum in sorted({r["stratum"] for r in rows}):
        subset = [r for r in rows if r["stratum"] == stratum]
        _, _, _, false_pos, false_neg = score(subset, detector, use_pages=use_pages)
        strata.add_row(
            stratum,
            str(len(subset)),
            str(sum(row["label"] for row in subset)),
            str(false_pos),
            str(false_neg),
        )
    console.print(strata)
    console.print()


if __name__ == "__main__":
    toc = load_dataset("toc_validation_set.jsonl")
    report(
        "looks_like_table_of_contents (as search runs it, with page data)",
        toc,
        looks_like_table_of_contents,
        use_pages=True,
    )
    report(
        "looks_like_table_of_contents (text only, as the unit tests see it)",
        toc,
        looks_like_table_of_contents,
        use_pages=False,
    )
    report(
        "looks_like_reference_list",
        load_dataset("reflist_validation_set.jsonl"),
        lambda text, _pages: looks_like_reference_list(text),
        use_pages=False,
    )
