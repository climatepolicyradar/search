from dataclasses import dataclass, field

from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.otel.span_tree import SpanTree


@dataclass
class Result:
    id: str
    text: str = ""


@dataclass
class Results:
    results: list[Result] = field(default_factory=list)
    total_size: int | None = None


@dataclass
class Pair:
    first: Results
    second: Results


def results(*ids: str) -> Results:
    return Results(results=[Result(id=id) for id in ids])


def context[O](output: O) -> EvaluatorContext[str, O, object]:
    return EvaluatorContext(
        name=None,
        inputs="",
        metadata=None,
        expected_output=None,
        output=output,
        duration=0.0,
        _span_tree=SpanTree(),
        attributes={},
        metrics={},
    )
