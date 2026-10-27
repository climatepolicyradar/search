from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance_tests.evaluators.evaluator import HasId, HasResults


@dataclass
class Forbidden[I](Evaluator[I, HasResults[HasId], object]):
    forbidden: list[str]
    k: int = 10
    threshold: float = 1.0

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasResults[HasId], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of forbidden IDs absent from the top k results."""
        top_k = {result.id for result in ctx.output.results[: self.k]}
        present = [id for id in self.forbidden if id in top_k]
        reason = f"forbidden in top {self.k}: {present}" if present else None
        score = (len(self.forbidden) - len(present)) / len(self.forbidden)

        return {
            "Forbidden": EvaluationReason(value=score, reason=reason),
            "Forbidden passed": EvaluationReason(
                value=score >= self.threshold,
                reason=reason,
            ),
        }
