from pydantic_evals.evaluators import EvaluationReason

from relevance.evaluators.recall import Recall
from relevance.tests.fakes import context, results


def test_all_expected_in_top_k_passes() -> None:
    outcome = Recall(expected=["a", "b"], k=3).evaluate(context(results("b", "x", "a")))
    assert outcome == {
        "Recall": EvaluationReason(value=1.0, reason=None),
        "Recall passed": EvaluationReason(value=True, reason=None),
    }


def test_an_expected_result_beyond_k_is_missing_and_named() -> None:
    outcome = Recall(expected=["a", "b"], k=2).evaluate(context(results("a", "x", "b")))
    reason = "missing from top 2: ['b']"
    assert outcome == {
        "Recall": EvaluationReason(value=0.5, reason=reason),
        "Recall passed": EvaluationReason(value=False, reason=reason),
    }


def test_a_partial_score_passes_at_or_above_the_threshold() -> None:
    evaluator = Recall(expected=["a", "b"], k=2, threshold=0.5)
    outcome = evaluator.evaluate(context(results("a", "x")))
    reason = "missing from top 2: ['b']"
    assert outcome == {
        "Recall": EvaluationReason(value=0.5, reason=reason),
        "Recall passed": EvaluationReason(value=True, reason=reason),
    }
