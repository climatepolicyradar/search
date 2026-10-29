from pydantic_evals.evaluators import EvaluationReason

from relevance.evaluators.forbidden import Forbidden
from relevance.tests.fakes import context, results


def test_no_forbidden_results_passes() -> None:
    outcome = Forbidden(forbidden=["x"], k=2).evaluate(context(results("a", "b")))
    assert outcome == {
        "Forbidden": EvaluationReason(value=1.0, reason=None),
        "Forbidden passed": EvaluationReason(value=True, reason=None),
    }


def test_a_forbidden_result_in_top_k_fails_and_is_named() -> None:
    outcome = Forbidden(forbidden=["x", "y"], k=2).evaluate(context(results("a", "x")))
    reason = "forbidden in top 2: ['x']"
    assert outcome == {
        "Forbidden": EvaluationReason(value=0.5, reason=reason),
        "Forbidden passed": EvaluationReason(value=False, reason=reason),
    }


def test_a_forbidden_result_beyond_k_passes() -> None:
    outcome = Forbidden(forbidden=["x"], k=2).evaluate(context(results("a", "b", "x")))
    assert outcome == {
        "Forbidden": EvaluationReason(value=1.0, reason=None),
        "Forbidden passed": EvaluationReason(value=True, reason=None),
    }
