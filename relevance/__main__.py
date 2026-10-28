from contextlib import AbstractContextManager, nullcontext
from datetime import datetime
from enum import StrEnum, auto
from typing import Annotated, Any

import typer
from pydantic_evals.reporting import EvaluationReport
from wandb import Run

from relevance.reporters import html_report, weights_and_biases
from relevance.suites import documents, labels, passages, principals
from search.config import TEST_RESULTS_DIR

app = typer.Typer()


class Suite(StrEnum):
    labels = auto()
    documents = auto()
    document_comparisons = auto()
    principals = auto()
    principal_comparisons = auto()
    passages = auto()
    passage_comparisons = auto()


class Report(StrEnum):
    html = auto()
    wandb = auto()


def run_suite(
    suite: Suite,
) -> EvaluationReport[Any, Any, dict[str, str]]:
    match suite:
        case Suite.labels:
            return labels.dataset.evaluate_sync(
                labels.run_search,
                max_concurrency=4,
            )
        case Suite.documents:
            return documents.dataset.evaluate_sync(
                documents.run_search,
                max_concurrency=4,
            )
        case Suite.document_comparisons:
            return documents.comparisons.evaluate_sync(
                documents.run_pair,
                max_concurrency=4,
            )
        case Suite.principals:
            return principals.dataset.evaluate_sync(
                principals.run_search,
                max_concurrency=4,
            )
        case Suite.principal_comparisons:
            return principals.comparisons.evaluate_sync(
                principals.run_pair,
                max_concurrency=4,
            )
        case Suite.passages:
            return passages.dataset.evaluate_sync(
                passages.run_search,
                max_concurrency=4,
            )
        case Suite.passage_comparisons:
            return passages.comparisons.evaluate_sync(
                passages.run_pair,
                max_concurrency=4,
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


def _write_html(report: EvaluationReport[Any, Any, dict[str, str]]) -> None:
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
