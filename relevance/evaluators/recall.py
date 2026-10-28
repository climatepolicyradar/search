from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance.evaluators.evaluator import HasId, HasResults


@dataclass
class Recall[I](Evaluator[I, HasResults[HasId], object]):
    expected: list[str]
    k: int = 10
    threshold: float = 1.0

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasResults[HasId], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of expected IDs found in the top k results."""
        top_k = {result.id for result in ctx.output.results[: self.k]}
        missing = [id for id in self.expected if id not in top_k]
        reason = f"missing from top {self.k}: {missing}" if missing else None
        score = (len(self.expected) - len(missing)) / len(self.expected)

        return {
            "Recall": EvaluationReason(value=score, reason=reason),
            "Recall passed": EvaluationReason(
                value=score >= self.threshold,
                reason=reason,
            ),
        }
