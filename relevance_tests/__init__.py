from collections import defaultdict
from pathlib import Path
from typing import Generic, Sequence, TypeVar

from knowledge_graph.identifiers import Identifier
from prefect import get_run_logger, task
from prefect.cache_policies import NO_CACHE
from prefect.futures import wait
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from search.document import Document
from search.engines import SearchEngine
from search.engines.json import serialise_pydantic_list_as_jsonl
from search.label import Label
from search.log import get_logger
from search.passage import Passage
from search.testcase import TestCase

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
# Constrained TypeVar matching SearchEngine's TModel
TModel = TypeVar("TModel", Document, Label, Passage)
console = Console()


class TestResult(BaseModel, Generic[T]):
    """A result of a test-case run against a search engine"""

    test_case: TestCase
    passed: bool
    search_engine_id: Identifier
    search_results: list[T]


def save_test_results_as_jsonl(test_results: list[TestResult], file_path: Path) -> None:
    """Save test results to a JSONL file"""

    jsonl_results = serialise_pydantic_list_as_jsonl(test_results)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(jsonl_results)
    logger.info(f"Saved test results to {file_path}")


def generate_test_run_id(
    engine: SearchEngine, test_cases: list[TestCase], test_results: list[TestResult]
) -> Identifier:
    """Generate a unique identifier for a test run"""

    test_run_id = Identifier.generate(engine.name, *test_cases, *test_results)
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
    - failed: the number that didn't pass
    - total: the number of tests
    - pass rate: passed/total
    """

    results_by_category: dict[str, list[TestResult]] = defaultdict(list)

    for result in test_results:
        category = result.test_case.category
        if category is None:
            category = "uncategorized"
        results_by_category[category].append(result)

    metrics: dict[str, dict[str, int | float | list[TestResult]]] = dict()

    total_passed = sum(1 for r in test_results if r.passed)
    num_test_results = len(test_results)
    metrics["overall"] = {
        "results": test_results,
        "passed": total_passed,
        "failed": num_test_results - total_passed,
        "total": num_test_results,
        "pass_rate": total_passed / num_test_results if num_test_results > 0 else 0,
    }

    category_pass_rates: list[float] = []
    for category in sorted(results_by_category.keys()):
        results: list[TestResult] = results_by_category[category]
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        pass_rate = passed / total if total > 0 else 0
        category_pass_rates.append(pass_rate)

        metrics[category] = {
            "results": results,
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": pass_rate,
        }

    macro_avg = (
        sum(category_pass_rates) / len(category_pass_rates)
        if category_pass_rates
        else 0
    )
    metrics["macro_average"] = {
        "pass_rate": macro_avg,
    }

    return metrics


def print_test_results(test_results: list[TestResult]) -> None:
    """Print test results as a rich table showing pass/fail counts per category, using calculate_test_result_metrics."""

    metrics = calculate_test_result_metrics(test_results)
    table = Table(
        title="Test Results Summary", show_header=True, header_style="bold magenta"
    )
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Passed", style="green", justify="right")
    table.add_column("Total", style="blue", justify="right")
    table.add_column("Pass Rate", style="yellow", justify="right")

    excluded_keys = {"overall", "macro_average"}
    for category in sorted(k for k in metrics.keys() if k not in excluded_keys):
        cat = metrics[category]
        passed = cat["passed"]
        total = cat["total"]
        pass_rate = f"{(cat['pass_rate'] * 100):.1f}%" if total > 0 else "N/A"
        table.add_row(category, str(passed), str(total), pass_rate)

    overall = metrics["overall"]
    total_passed = overall["passed"]
    total_tests = overall["total"]
    total_pass_rate = (
        f"{(overall['pass_rate'] * 100):.1f}%" if total_tests > 0 else "N/A"
    )
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_passed}[/bold]",
        f"[bold]{total_tests}[/bold]",
        f"[bold]{total_pass_rate}[/bold]",
        style="bold",
    )

    console.print(table)
    console.print()

    has_failures = False
    for category in sorted(k for k in metrics.keys() if k not in excluded_keys):
        cat = metrics[category]
        failures = [r for r in cat["results"] if not r.passed]  # type: ignore

        if failures:
            has_failures = True
            console.print(f"[bold red]Failures in category '{category}':[/bold red]")
            for failure in failures:
                console.print(
                    f"  • [yellow]{failure.test_case.name}[/yellow]: {failure.test_case.search_terms}"
                )
                console.print(f"    Description: {failure.test_case.description}")
                console.print()

    if not has_failures:
        console.print("[bold green]✓ All tests passed![/bold green]")


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
        try:
            test_passed, search_results = test_case.run_against(engine)
        except Exception as e:
            logger.info(f"Test case {test_case} failed with exception", exc_info=e)

        test_result = TestResult(
            test_case=test_case,
            passed=test_passed,
            search_engine_id=engine.id,
            search_results=search_results,
        )
        engine_test_results.append(test_result)

    print_test_results(engine_test_results)
    wb.log_test_results(
        test_results=engine_test_results,
        primitive=primitive_type,
        search_engine=engine,
    )

    test_run_id = generate_test_run_id(engine, test_cases, engine_test_results)
    output_file_path = (
        TEST_RESULTS_DIR / output_subdir / f"{engine.name}_{test_run_id}.jsonl"
    )

    save_test_results_as_jsonl(engine_test_results, output_file_path)


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
    wait(
        [
            run_tests_for_engine.submit(
                engine, test_cases, primitive_type, output_subdir
            )
            for engine in engines
        ]
    )
