import json
from contextlib import AbstractContextManager, nullcontext
from datetime import datetime
from enum import StrEnum, auto
from functools import partial
from typing import Annotated, Any

import typer
from opentelemetry.metrics import Meter
from pydantic_evals.reporting import EvaluationReport
from wandb import Run

from relevance.api.client import SearchClient
from relevance.reporters import html, otel, weights_and_biases
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
    otel = auto()


def run_suite(
    suite: Suite,
    client: SearchClient,
) -> EvaluationReport[Any, Any, dict[str, str]]:
    match suite:
        case Suite.labels:
            return labels.dataset.evaluate_sync(
                partial(labels.run_search, client),
                max_concurrency=4,
            )
        case Suite.documents:
            return documents.dataset.evaluate_sync(
                partial(documents.run_search, client),
                max_concurrency=4,
            )
        case Suite.document_comparisons:
            return documents.comparisons.evaluate_sync(
                partial(documents.run_pair, client),
                max_concurrency=4,
            )
        case Suite.principals:
            return principals.dataset.evaluate_sync(
                partial(principals.run_search, client),
                max_concurrency=4,
            )
        case Suite.principal_comparisons:
            return principals.comparisons.evaluate_sync(
                partial(principals.run_pair, client),
                max_concurrency=4,
            )
        case Suite.passages:
            return passages.dataset.evaluate_sync(
                partial(passages.run_search, client),
                max_concurrency=4,
            )
        case Suite.passage_comparisons:
            return passages.comparisons.evaluate_sync(
                partial(passages.run_pair, client),
                max_concurrency=4,
            )


SuiteParam = Annotated[Suite, typer.Option()]
ReportParam = Annotated[list[Report] | None, typer.Option("--report")]
UrlParam = Annotated[str | None, typer.Option()]


def _init_wandb(
    suite: Suite,
    reports: list[Report],
) -> AbstractContextManager[Run | None]:
    if Report.wandb in reports:
        return weights_and_biases.init(suite)
    return nullcontext()


def _init_otel(
    suite: Suite,
    reports: list[Report],
) -> AbstractContextManager[Meter | None]:
    if Report.otel in reports:
        return otel.init(suite)
    return nullcontext()


def _write_html(report: EvaluationReport[Any, Any, dict[str, str]]) -> None:
    name = f"{report.dataset_name or 'report'}_{datetime.now():%Y%m%d_%H%M}.html"
    html.report(report, (path := TEST_RESULTS_DIR / name))
    typer.echo(f"HTML report written to {path}")


@app.command()
def suites() -> None:
    typer.echo(json.dumps([suite.value for suite in Suite]))


@app.command()
def run(
    suite: SuiteParam,
    reports: ReportParam = None,
    url: UrlParam = None,
) -> None:
    reports = reports or []

    with (
        SearchClient.create(url) as client,
        _init_wandb(suite, reports) as run,
        _init_otel(suite, reports) as meter,
    ):
        report = run_suite(suite, client)
        if run is not None:
            weights_and_biases.report(run, report)
        if meter is not None:
            otel.report(meter, suite, report)
        if Report.html in reports:
            _write_html(report)
        report.print(include_reasons=True)


if __name__ == "__main__":
    app()
