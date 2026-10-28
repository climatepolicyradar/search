from pydantic_evals.evaluators import EvaluationReason

from relevance.evaluators.overlap import Overlap
from relevance.tests.fakes import Pair, context, results


def test_identical_lists_fully_overlap() -> None:
    evaluator = Overlap(k=3)
    pair = Pair(first=results("a", "b", "c"), second=results("c", "b", "a"))
    outcome = evaluator.evaluate(context(pair))
    reason = "3/3 overlap; only in first: []; only in second: []"
    assert outcome == {
        "Overlap": EvaluationReason(value=1.0, reason=reason),
        "Overlap passed": EvaluationReason(value=True, reason=reason),
    }


def test_a_partial_overlap_fails_below_the_threshold() -> None:
    evaluator = Overlap(k=4)
    pair = Pair(first=results("a", "b", "c", "d"), second=results("a", "b", "c", "x"))
    outcome = evaluator.evaluate(context(pair))
    reason = "3/4 overlap; only in first: ['d']; only in second: ['x']"
    assert outcome == {
        "Overlap": EvaluationReason(value=0.75, reason=reason),
        "Overlap passed": EvaluationReason(value=False, reason=reason),
    }


def test_a_partial_overlap_passes_at_the_threshold() -> None:
    evaluator = Overlap(k=4, threshold=0.75)
    pair = Pair(first=results("a", "b", "c", "d"), second=results("a", "b", "c", "x"))
    outcome = evaluator.evaluate(context(pair))
    reason = "3/4 overlap; only in first: ['d']; only in second: ['x']"
    assert outcome == {
        "Overlap": EvaluationReason(value=0.75, reason=reason),
        "Overlap passed": EvaluationReason(value=True, reason=reason),
    }


def test_only_the_top_k_are_compared() -> None:
    evaluator = Overlap(k=2)
    pair = Pair(first=results("a", "b", "x"), second=results("a", "b", "y"))
    outcome = evaluator.evaluate(context(pair))
    reason = "2/2 overlap; only in first: []; only in second: []"
    assert outcome == {
        "Overlap": EvaluationReason(value=1.0, reason=reason),
        "Overlap passed": EvaluationReason(value=True, reason=reason),
    }


def test_strict_order_counts_only_same_position_matches() -> None:
    evaluator = Overlap(k=3, strict_order=True)
    pair = Pair(first=results("a", "b", "c"), second=results("a", "c", "b"))
    outcome = evaluator.evaluate(context(pair))
    reason = "1/3 overlap; only in first: []; only in second: []"
    assert outcome == {
        "Overlap": EvaluationReason(value=1 / 3, reason=reason),
        "Overlap passed": EvaluationReason(value=False, reason=reason),
    }


def test_the_shorter_list_is_the_denominator() -> None:
    evaluator = Overlap(k=3)
    pair = Pair(first=results("a", "b", "c"), second=results("a", "b"))
    outcome = evaluator.evaluate(context(pair))
    reason = "2/2 overlap; only in first: ['c']; only in second: []"
    assert outcome == {
        "Overlap": EvaluationReason(value=1.0, reason=reason),
        "Overlap passed": EvaluationReason(value=True, reason=reason),
    }


def test_an_empty_list_scores_zero() -> None:
    outcome = Overlap(k=3).evaluate(context(Pair(first=results("a"), second=results())))
    reason = "0/0 overlap; only in first: ['a']; only in second: []"
    assert outcome == {
        "Overlap": EvaluationReason(value=0.0, reason=reason),
        "Overlap passed": EvaluationReason(value=False, reason=reason),
    }
