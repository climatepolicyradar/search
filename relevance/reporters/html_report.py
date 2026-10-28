from pathlib import Path

from pydantic_evals.reporting import EvaluationReport
from rich.console import Console


def report[O](report: EvaluationReport[str, O, dict[str, str]], path: Path) -> None:
    console = Console(record=True)
    report.print(console=console, include_reasons=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    console.save_html(str(path))
