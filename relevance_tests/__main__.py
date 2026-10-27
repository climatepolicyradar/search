from contextlib import AbstractContextManager, nullcontext
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

import typer
from pydantic_evals.reporting import EvaluationReport
from wandb import Run

from relevance_tests import evals_labels
from relevance_tests.reporters import html_report, weights_and_biases
from search.config import TEST_RESULTS_DIR

app = typer.Typer()


class Suite(StrEnum):
    labels = "labels"


class Report(StrEnum):
    html = "html"
    wandb = "wandb"


def run_suite(
    suite: Suite,
) -> EvaluationReport[str, Any, dict[str, str]]:
    match suite:
        case Suite.labels:
            return evals_labels.dataset.evaluate_sync(
                evals_labels.run_search,
                max_concurrency=8,
            )


SuiteParam = Annotated[Suite, typer.Option()]
ReportParam = Annotated[list[Report] | None, typer.Option("--report")]


def _init_wandb(
    suite: Suite,
    reports: list[Report],
) -> AbstractContextManager[Run | None]:
    if Report.wandb in reports:
        return weights_and_biases.init(suite)
    return nullcontext()


def _write_html(report: EvaluationReport[str, Any, dict[str, str]]) -> None:
    name = f"{report.dataset_name or 'report'}_{datetime.now():%Y%m%d_%H%M}.html"
    html_report.report(report, (path := TEST_RESULTS_DIR / name))
    print(f"HTML report written to {path}")


@app.command()
def main(suite: SuiteParam, reports: ReportParam = None) -> None:
    reports = reports or []

    with _init_wandb(suite, reports) as run:
        report = run_suite(suite)
        if run is not None:
            weights_and_biases.report(run, report)
        if Report.html in reports:
            _write_html(report)
        report.print(include_reasons=True)


if __name__ == "__main__":
    app()
