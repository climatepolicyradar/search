from pydantic_evals.evaluators import EvaluationResult
from pydantic_evals.evaluators.spec import EvaluatorSpec
from pydantic_evals.reporting import EvaluationReport, ReportCase

from relevance.reporters.otel import score_averages


def score(name: str, value: float) -> EvaluationResult[int | float]:
    return EvaluationResult(
        name=name,
        value=value,
        reason=None,
        source=EvaluatorSpec(name="Recall", arguments=None),
    )


def case(scores: dict[str, EvaluationResult[int | float]]) -> ReportCase[str, str, None]:
    return ReportCase(
        name="case",
        inputs="",
        metadata=None,
        expected_output=None,
        output="",
        metrics={},
        attributes={},
        scores=scores,
        labels={},
        assertions={},
        task_duration=0.0,
        total_duration=0.0,
    )


def test_same_named_scores_in_one_case_average_under_one_name() -> None:
    duplicated = case({"recall@5": score("recall@5", 1.0), "recall@5_2": score("recall@5", 0.0)})
    single = case({"recall@5": score("recall@5", 0.5), "recall@10": score("recall@10", 1.0)})
    report = EvaluationReport[str, str, None](name="suite", cases=[duplicated, single])
    assert score_averages(report) == {"recall@5": 0.5, "recall@10": 1.0}
