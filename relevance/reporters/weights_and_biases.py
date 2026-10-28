import os
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import wandb
from pydantic import BaseModel
from pydantic_evals.reporting import EvaluationReport
from wandb import Run

from search import config


def init(dataset_name: str) -> Run:
    branch = os.getenv("GITHUB_REF_NAME", "local")
    return wandb.init(
        name=f"{branch}-{datetime.now():%y-%m-%d-%H%M}",
        project=f"search_relevance_{dataset_name}",
        config={"dataset": dataset_name},
        entity=config.WANDB_ENTITY,
        mode="online",
    )


def _inputs(inputs: object) -> dict[str, Any]:
    return (
        inputs.model_dump(mode="json")
        if isinstance(inputs, BaseModel)
        else {"query": str(inputs)}
    )


def _table(
    rows: list[dict[str, Any]],
    outputs: list[str],
    scores: list[str],
) -> wandb.EvalTable:
    present = list(dict.fromkeys(key for row in rows for key in row))
    inputs = [col for col in present if col not in [*outputs, *scores]]
    columns = [*inputs, *scores, *[col for col in outputs if col in present]]
    data: list[Iterable[Any]] = [[row.get(col) for col in columns] for row in rows]
    return wandb.EvalTable(
        input_columns=inputs,
        score_columns=scores,
        columns=[*columns],
        data=data,
    )


def report[I, O](run: Run, report: EvaluationReport[I, O, dict[str, str]]) -> None:
    cases: list[dict[str, Any]] = []

    for case in report.cases:
        failing = [
            f"{name}: {assertion.reason}"
            for name, assertion in case.assertions.items()
            if not assertion.value
        ]
        cases.append(
            {
                "case": case.name,
                **(case.metadata or {}),
                **_inputs(case.inputs),
                "passed": not failing,
                **{name: score.value for name, score in case.scores.items()},
                "failures": "; ".join(failing),
            }
        )

    for failure in report.failures:
        cases.append(
            {
                "case": failure.name,
                **(failure.metadata or {}),
                **_inputs(failure.inputs),
                "error": failure.error_message,
            }
        )

    if averages := report.averages():
        run.summary.update({**averages.scores, "pass rate": averages.assertions})

    run.summary["errored"] = len(report.failures)
    scores = list(dict.fromkeys(name for case in report.cases for name in case.scores))
    table = _table( cases, outputs=["failures", "error"], scores=["passed", *scores])
    run.log({"cases": table})
