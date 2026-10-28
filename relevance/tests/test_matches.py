from dataclasses import dataclass
from typing import Literal

import pytest
from pydantic_evals.evaluators import EvaluationReason

from relevance.evaluators.matches import Matches
from relevance.tests.fakes import Result, Results, context


@dataclass
class TextMatches(Matches[str, Result]):
    def text(self, result: Result) -> str:
        return result.text


def texts(*texts: str) -> Results:
    return Results(
        results=[Result(id=str(i), text=text) for i, text in enumerate(texts)]
    )


def test_all_passes_when_every_result_matches() -> None:
    evaluator = TextMatches(pattern="mango", k=2)
    outcome = evaluator.evaluate(context(texts("mango tree", "green mango")))
    reason = "2/2 of top 2 match"
    assert outcome == {
        "Matches": EvaluationReason(value=1.0, reason=reason),
        "Matches passed": EvaluationReason(value=True, reason=reason),
    }


def test_all_fails_when_one_result_does_not_match() -> None:
    evaluator = TextMatches(pattern="mango", k=2)
    outcome = evaluator.evaluate(context(texts("mango tree", "apple")))
    reason = "1/2 of top 2 match"
    assert outcome == {
        "Matches": EvaluationReason(value=0.5, reason=reason),
        "Matches passed": EvaluationReason(value=False, reason=reason),
    }


def test_any_passes_with_a_single_match() -> None:
    evaluator = TextMatches(pattern="mango", k=3, all_or_any="any")
    outcome = evaluator.evaluate(context(texts("apple", "pear", "mango")))
    reason = "1/3 of top 3 match"
    assert outcome == {
        "Matches": EvaluationReason(value=1 / 3, reason=reason),
        "Matches passed": EvaluationReason(value=True, reason=reason),
    }


def test_results_beyond_k_are_ignored() -> None:
    evaluator = TextMatches(pattern="mango", k=1)
    outcome = evaluator.evaluate(context(texts("mango", "apple")))
    reason = "1/1 of top 1 match"
    assert outcome == {
        "Matches": EvaluationReason(value=1.0, reason=reason),
        "Matches passed": EvaluationReason(value=True, reason=reason),
    }


@pytest.mark.parametrize("all_or_any", ["all", "any"])
def test_no_results_fails(all_or_any: Literal["all", "any"]) -> None:
    evaluator = TextMatches(pattern="mango", all_or_any=all_or_any)
    outcome = evaluator.evaluate(context(texts()))
    assert outcome == {
        "Matches": EvaluationReason(value=0.0, reason="no results"),
        "Matches passed": EvaluationReason(value=False, reason="no results"),
    }
