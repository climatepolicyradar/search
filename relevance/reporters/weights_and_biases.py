from collections.abc import Iterable
from typing import Any

import wandb
from pydantic_evals.reporting import EvaluationReport
from wandb import Run

from search import config


def init(dataset_name: str) -> Run:
    return wandb.init(
        config={"dataset": dataset_name},
        project="search_relevance",
        entity=config.WANDB_ENTITY,
        mode="online",
    )


def report[O](run: Run, report: EvaluationReport[str, O, dict[str, str]]) -> None:
    rows: list[dict[str, Any]] = []
    for case in report.cases:
        rows.append(
            {
                "case": case.name,
                "query": str(case.inputs),
                **(case.metadata or {}),
                **{name: result.value for name, result in case.scores.items()},
                **{name: result.value for name, result in case.assertions.items()},
            }
        )

    for failure in report.failures:
        rows.append(
            {
                "case": failure.name,
                "query": str(failure.inputs),
                **(failure.metadata or {}),
                "error": failure.error_message,
            }
        )

    columns = list(dict.fromkeys(key for row in rows for key in row))
    data: list[Iterable[Any]] = [[row.get(col) for col in columns] for row in rows]
    table = wandb.Table(columns=[*columns], data=data)

    if averages := report.averages():
        run.summary.update({**averages.scores, "pass rate": averages.assertions})

    run.summary["errored"] = len(report.failures)
    run.log({"cases": table})
