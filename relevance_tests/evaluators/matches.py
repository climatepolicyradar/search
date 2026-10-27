import re
from abc import abstractmethod
from dataclasses import dataclass
from typing import Literal

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance_tests.evaluators.evaluator import HasResults


@dataclass
class Matches[T](Evaluator[str, HasResults[T], object]):
    pattern: str
    k: int = 20
    all_or_any: Literal["all", "any"] = "all"

    @abstractmethod
    def text(self, result: T) -> str:
        """The text of a result to match the pattern against."""
        ...

    def evaluate(
        self,
        ctx: EvaluatorContext[str, HasResults[T], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of the top k results whose text matches the pattern."""
        regex = re.compile(self.pattern)
        if top_k := ctx.output.results[: self.k]:
            matching = sum(1 for result in top_k if regex.search(self.text(result)))
            reason = f"{matching}/{len(top_k)} of top {self.k} match"
            score = matching / len(top_k)
            passed = score == 1.0 if self.all_or_any == "all" else matching > 0
        else:
            reason = "no results"
            score = 0.0
            passed = False

        return {
            "Matches": EvaluationReason(value=score, reason=reason),
            "Matches passed": EvaluationReason(
                value=passed,
                reason=reason,
            ),
        }
