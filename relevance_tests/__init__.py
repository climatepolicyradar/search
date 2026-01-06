from collections import defaultdict
from pathlib import Path
from typing import Generic, TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from search.engines import SearchEngine
from search.engines.json import serialise_pydantic_list_as_jsonl
from search.logging import get_logger
from search.testcase import TestCase

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
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


def print_test_results(test_results: list[TestResult]) -> None:
    """Print test results as a rich table showing pass/fail counts per category."""

    category_results: dict[str, list[TestResult]] = defaultdict(list)

    for result in test_results:
        category = result.test_case.category
        if category is None:
            category = "uncategorized"
        category_results[category].append(result)

    table = Table(
        title="Test Results Summary", show_header=True, header_style="bold magenta"
    )
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Passed", style="green", justify="right")
    table.add_column("Total", style="blue", justify="right")
    table.add_column("Pass Rate", style="yellow", justify="right")

    for category in sorted(category_results.keys()):
        results = category_results[category]
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        pass_rate = f"{(passed / total * 100):.1f}%" if total > 0 else "N/A"

        table.add_row(category, str(passed), str(total), pass_rate)

    total_passed = sum(1 for r in test_results if r.passed)
    total_tests = len(test_results)
    total_pass_rate = (
        f"{(total_passed / total_tests * 100):.1f}%" if total_tests > 0 else "N/A"
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
    for category in sorted(category_results.keys()):
        results = category_results[category]
        failures = [r for r in results if not r.passed]

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
