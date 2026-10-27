from pydantic_evals.evaluators import EvaluationReason

from relevance_tests.evaluators.precision import Precision
from relevance_tests.tests.fakes import context, results


def test_all_expected_in_top_k_passes() -> None:
    evaluator = Precision(expected=["a", "b"], k=2)
    outcome = evaluator.evaluate(context(results("a", "b", "c")))
    assert outcome == {
        "Precision": EvaluationReason(value=1.0, reason=None),
        "Precision passed": EvaluationReason(value=True, reason=None),
    }


def test_an_unexpected_result_fails_and_is_named() -> None:
    outcome = Precision(expected=["a", "b"], k=2).evaluate(context(results("a", "x")))
    reason = "unexpected in top 2: ['x']"
    assert outcome == {
        "Precision": EvaluationReason(value=0.5, reason=reason),
        "Precision passed": EvaluationReason(value=False, reason=reason),
    }


def test_fewer_results_than_k_counts_against_the_score() -> None:
    outcome = Precision(expected=["a", "b"], k=2).evaluate(context(results("a")))
    reason = "only 1 results returned"
    assert outcome == {
        "Precision": EvaluationReason(value=0.5, reason=reason),
        "Precision passed": EvaluationReason(value=False, reason=reason),
    }


def test_a_partial_score_passes_at_or_above_the_threshold() -> None:
    evaluator = Precision(expected=["a"], k=2, threshold=0.5)
    outcome = evaluator.evaluate(context(results("a", "x")))
    reason = "unexpected in top 2: ['x']"
    assert outcome == {
        "Precision": EvaluationReason(value=0.5, reason=reason),
        "Precision passed": EvaluationReason(value=True, reason=reason),
    }
