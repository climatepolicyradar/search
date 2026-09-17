import copy
import logging
import time
from collections import defaultdict
from logging import LoggerAdapter
from pathlib import Path
from typing import Any, Generic, Literal, Sequence, TypeVar

from prefect.cache_policies import NO_CACHE
from prefect.futures import wait
from pydantic import BaseModel, model_validator
from rich.console import Console
from rich.table import Table

from prefect import get_run_logger, task
from search.data_in_models import Document
from search.engines import SearchEngine, VespaError
from search.identifiers import Identifier, generate_id
from search.label import Label
from search.log import get_logger
from search.passage import Passage
from search.testcase import TestCase, TestCaseOutcome

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
# Constrained TypeVar matching SearchEngine's TModel
TModel = TypeVar("TModel", Document, Label, Passage)
console = Console()


TestStatus = Literal["passed", "failed", "errored"]


class RelevanceRunIncompleteError(Exception):
    """Raised when a run finished with cases that could not be evaluated."""


class TestResult(BaseModel, Generic[T]):
    """
    A result of a test-case run against a search engine.

    ``status`` is a tagged result rather than a bool because "this document
    ranked badly" and "we never got an answer" are different facts, and a
    ``passed=False`` carrying an empty result set cannot tell them apart - the
    semipredicate problem described in ``docs/errors.md``. An ``errored`` case
    has no verdict, so it is excluded from pass rates rather than counted
    against them.
    """

    test_case: TestCase
    status: TestStatus
    error: str | None = None
    search_engine_id: str
    search_results: list[T]
    comparison_search_results: list[T] | None = None
    debug_info: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def check_error_matches_status(self):
        """An errored result carries an error, and nothing else does."""
        if (self.status == "errored") != (self.error is not None):
            raise ValueError(
                "error must be set if and only if status is 'errored' "
                f"(got status={self.status!r}, error={self.error!r})"
            )
        return self


def save_test_results_as_jsonl(test_results: list[TestResult], file_path: Path) -> None:
    """Save test results to a JSONL file"""

    file_path.parent.mkdir(parents=True, exist_ok=True)
    # Written a result at a time: results carrying debug info are large, and holding
    # the whole serialised file in memory as one string has OOM-killed runs.
    with file_path.open("w") as file:
        for i, test_result in enumerate(test_results):
            if i:
                file.write("\n")
            file.write(test_result.model_dump_json())
    logger.info(f"Saved test results to {file_path}")


def save_test_results_as_html(
    test_results: list[TestResult],
    file_path: Path,
    engine_name: str,
    test_run_id: str,
) -> None:
    """Save test results as a self-contained HTML report for domain-expert review."""
    from relevance_tests.html_report import render_test_results_html

    html = render_test_results_html(
        test_results=test_results,
        engine_name=engine_name,
        test_run_id=test_run_id,
    )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(html)
    logger.info(f"Saved HTML test report to {file_path}")


def generate_test_run_id(
    engine: SearchEngine, test_cases: list[TestCase], test_results: list[TestResult]
) -> Identifier:
    """Generate a unique identifier for a test run"""

    test_run_id = generate_id(engine.name, *test_cases, *test_results)
    logger.info(f"Generated test run id: {test_run_id}")
    return test_run_id


def calculate_test_result_metrics(
    test_results: list[TestResult],
) -> dict[str, dict[str, int | float | list[TestResult]]]:
    """
    Calculate test result pass rates by category and overall.

    Returns a dict of dicts keyed by category with an extra "overall" key.

    Each subdictionary has the keys:
    - results: a list of TestResults per category
    - passed: the number that passed
    - failed: the number that were evaluated and did not pass
    - errored: the number that could not be evaluated at all
    - total: the number of tests run
    - pass_rate: passed/(total - errored)

    Errored cases are excluded from the pass-rate denominator. They carry no
    verdict, so counting them as failures under-reports the pass rate and makes
    an infrastructure blip look like a relevance regression (FUS-479).
    """

    results_by_category: dict[str, list[TestResult]] = defaultdict(list)

    for result in test_results:
        category = result.test_case.category
        if category is None:
            category = "uncategorized"
        results_by_category[category].append(result)

    metrics: dict[str, dict[str, int | float | list[TestResult]]] = dict()

    metrics["overall"] = {
        "results": test_results,
        **_counts(test_results),
    }

    category_pass_rates: list[float] = []
    for category in sorted(results_by_category.keys()):
        results: list[TestResult] = results_by_category[category]
        counts = _counts(results)
        # A category in which nothing could be evaluated has no pass rate to
        # contribute; averaging in a 0.0 would report it as total failure.
        if counts["total"] - counts["errored"] > 0:
            category_pass_rates.append(counts["pass_rate"])

        metrics[category] = {"results": results, **counts}

    macro_avg = (
        sum(category_pass_rates) / len(category_pass_rates)
        if category_pass_rates
        else 0
    )
    metrics["macro_average"] = {
        "pass_rate": macro_avg,
    }

    return metrics


def _counts(test_results: list[TestResult]) -> dict[str, int | float]:
    """Pass/fail/error counts and the pass rate for one group of results."""
    passed = sum(1 for r in test_results if r.status == "passed")
    failed = sum(1 for r in test_results if r.status == "failed")
    errored = sum(1 for r in test_results if r.status == "errored")
    evaluated = passed + failed
    return {
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "total": len(test_results),
        "pass_rate": passed / evaluated if evaluated > 0 else 0,
    }


def print_test_results(test_results: list[TestResult]) -> None:
    """Print test results as a rich table showing pass/fail/error counts per category, using calculate_test_result_metrics."""

    metrics = calculate_test_result_metrics(test_results)
    table = Table(
        title="Test Results Summary", show_header=True, header_style="bold magenta"
    )
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Passed", style="green", justify="right")
    table.add_column("Errored", style="yellow", justify="right")
    table.add_column("Total", style="blue", justify="right")
    table.add_column("Pass Rate", style="yellow", justify="right")

    excluded_keys = {"overall", "macro_average"}
    for category in sorted(k for k in metrics.keys() if k not in excluded_keys):
        cat = metrics[category]
        evaluated = cat["total"] - cat["errored"]  # pyright: ignore[reportOperatorIssue]
        pass_rate = f"{(cat['pass_rate'] * 100):.1f}%" if evaluated > 0 else "N/A"  # pyright: ignore[reportOperatorIssue]
        table.add_row(
            category,
            str(cat["passed"]),
            str(cat["errored"]),
            str(cat["total"]),
            pass_rate,
        )

    overall = metrics["overall"]
    total_evaluated = overall["total"] - overall["errored"]  # pyright: ignore[reportOperatorIssue]
    total_pass_rate = (
        f"{(overall['pass_rate'] * 100):.1f}%" if total_evaluated > 0 else "N/A"  # pyright: ignore[reportOperatorIssue]
    )
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{overall['passed']}[/bold]",
        f"[bold]{overall['errored']}[/bold]",
        f"[bold]{overall['total']}[/bold]",
        f"[bold]{total_pass_rate}[/bold]",
        style="bold",
    )

    console.print(table)
    console.print("[dim]Pass rate excludes errored cases.[/dim]")
    console.print()

    has_failures = False
    has_errors = False
    for category in sorted(k for k in metrics.keys() if k not in excluded_keys):
        cat = metrics[category]
        results: list[TestResult] = cat["results"]  # type: ignore[assignment]
        failures = [r for r in results if r.status == "failed"]
        errors = [r for r in results if r.status == "errored"]

        if failures:
            has_failures = True
            console.print(f"[bold red]Failures in category '{category}':[/bold red]")
            for failure in failures:
                console.print(
                    f"  • [yellow]{failure.test_case.name}[/yellow]: {failure.test_case.search_terms}"
                )
                console.print(f"    Description: {failure.test_case.description}")
                diagnosis = failure.test_case.diagnose(failure.search_results)
                if diagnosis:
                    console.print("    Diagnosis:")
                    for line in diagnosis.split("\n"):
                        console.print(f"      {line}")
                console.print()

        if errors:
            has_errors = True
            # Not diagnosed: an empty result set produced by a failed request
            # says nothing about ranking.
            console.print(
                f"[bold yellow]Errored (not evaluated) in category "
                f"'{category}':[/bold yellow]"
            )
            for errored in errors:
                console.print(
                    f"  • [yellow]{errored.test_case.name}[/yellow]: {errored.test_case.search_terms}"
                )
                console.print(f"    Error: {errored.error}")
            console.print()

    if not has_failures and not has_errors:
        console.print("[bold green]✓ All tests passed![/bold green]")
    elif not has_failures:
        console.print(
            "[bold yellow]No relevance failures, but some cases could not be "
            "evaluated.[/bold yellow]"
        )


# One retry, because the failures this exists for are transient: a query that
# takes longer than its budget under contention succeeds on the next attempt.
VESPA_ATTEMPTS = 2
VESPA_RETRY_DELAY_SECONDS = 2


def _run_test_case(
    engine: SearchEngine[TModel],
    test_case: TestCase,
    logger: logging.Logger | LoggerAdapter,
) -> tuple[TestCaseOutcome | None, str | None]:
    """
    Run one test case, retrying a failed Vespa request.

    :returns: ``(outcome, None)`` if the case was evaluated, or
        ``(None, error)`` if it could not be - never a verdict invented from a
        failure. Every exception is reported as "not evaluated" rather than as a
        relevance failure, whatever its cause: a bug in a test case is no more a
        statement about ranking than a timeout is, and crashing the run here
        would discard the report for every other case.

    The retry covers ``VespaError`` only. Anything else is deterministic, so
    re-running it just costs time.
    """
    for attempt in range(1, VESPA_ATTEMPTS + 1):
        try:
            return test_case.run_against(engine), None
        except VespaError as e:
            if attempt < VESPA_ATTEMPTS:
                logger.warning(
                    f"Vespa request failed for {test_case.name}: "
                    f"{test_case.search_terms} (attempt {attempt} of "
                    f"{VESPA_ATTEMPTS}), retrying",
                    exc_info=e,
                )
                time.sleep(VESPA_RETRY_DELAY_SECONDS)
                continue
            logger.warning(
                f"Test case {test_case.name}: {test_case.search_terms} could not "
                f"be evaluated after {VESPA_ATTEMPTS} attempts",
                exc_info=e,
            )
            return None, f"{type(e).__name__}: {e}"
        except Exception as e:
            logger.warning(
                f"Test case {test_case.name}: {test_case.search_terms} could not "
                f"be evaluated",
                exc_info=e,
            )
            return None, f"{type(e).__name__}: {e}"

    raise AssertionError("unreachable: the loop returns on every path")


@task(cache_policy=NO_CACHE)
def run_tests_for_engine(
    engine: SearchEngine[TModel],
    test_cases: list[TestCase],
    primitive_type: type[TModel],
    output_subdir: str,
) -> None:
    """
    Run test cases for a single search engine and save results.

    :param engine: Search engine to test
    :param test_cases: List of test cases to run
    :param primitive_type: Type of model being tested (Document, Label, or Passage)
    :param output_subdir: Subdirectory name for saving results (e.g., "documents")
    """
    from search.config import TEST_RESULTS_DIR
    from search.weights_and_biases import WandbSession

    logger = get_run_logger()
    wb = WandbSession()

    engine_test_results: list[TestResult[TModel]] = []
    logger.info(f"Testing test cases against {engine.name}")

    for test_case in test_cases:
        logger.info(f"Running test case: {test_case.name}: {test_case.search_terms}")
        outcome, error = _run_test_case(engine, test_case, logger)

        raw_debug_info = getattr(engine, "last_debug_info", None)
        debug_info = copy.deepcopy(raw_debug_info) if raw_debug_info else None

        if outcome is None:
            # No debug info: `last_debug_info` still holds the previous case's
            # query, and attaching it here would attribute another query's
            # ranking scores to a case that never got an answer.
            test_result = TestResult(
                test_case=test_case,
                status="errored",
                error=error,
                search_engine_id=engine.id,
                search_results=[],
            )
        else:
            test_result = TestResult(
                test_case=test_case,
                status="passed" if outcome.passed else "failed",
                search_engine_id=engine.id,
                search_results=outcome.results,
                comparison_search_results=outcome.comparison_results,
                debug_info=debug_info,
            )
        engine_test_results.append(test_result)

    print_test_results(engine_test_results)
    wb.log_test_results(
        test_results=engine_test_results,
        primitive=primitive_type,  # pyright: ignore[reportArgumentType]
        search_engine=engine,  # pyright: ignore[reportArgumentType]
    )

    test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
    output_dir = TEST_RESULTS_DIR / output_subdir
    output_file_stem = output_dir / f"{engine.name}_{test_run_id}"

    save_test_results_as_jsonl(
        engine_test_results, output_file_stem.with_suffix(".jsonl")
    )
    save_test_results_as_html(
        engine_test_results,
        output_file_stem.with_suffix(".html"),
        engine_name=engine.name,
        test_run_id=str(test_run_id),
    )

    # Raised only once the report is on disk: the operator needs a red run *and*
    # something to read. A run with unevaluated cases has a pass rate that is not
    # comparable with any other run, which is the whole complaint in FUS-479.
    errored = [r for r in engine_test_results if r.status == "errored"]
    if errored:
        names = ", ".join(repr(r.test_case.search_terms) for r in errored)
        message = (
            f"{len(errored)} of {len(engine_test_results)} test cases could not be "
            f"evaluated against {engine.name}: {names}. "
            f"Report written to {output_file_stem.with_suffix('.html')}"
        )
        logger.error(message)
        raise RelevanceRunIncompleteError(message)


def run_relevance_tests_parallel(
    engines: Sequence[SearchEngine[TModel]],
    test_cases: list[TestCase],
    primitive_type: type[TModel],
    output_subdir: str,
) -> None:
    """
    Run relevance tests across multiple engines in parallel.

    :param engines: List of search engines to test
    :param test_cases: List of test cases to run
    :param primitive_type: Type of model being tested (Document, Label, or Passage)
    :param output_subdir: Subdirectory name for saving results (e.g., "documents")
    """
    futures = [
        run_tests_for_engine.submit(engine, test_cases, primitive_type, output_subdir)
        for engine in engines
    ]
    wait(futures)
    # `wait` reports which futures finished; it never re-raises, so without this
    # an engine whose run failed - including one that raised
    # RelevanceRunIncompleteError - would leave the flow green.
    for future in futures:
        future.result()
