from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance.evaluators.evaluator import HasId, HasResults


@dataclass
class Precision[I](Evaluator[I, HasResults[HasId], object]):
    expected: list[str]
    k: int = 10
    threshold: float = 1.0

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasResults[HasId], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of the top k results that are expected IDs."""
        top_k = [result.id for result in ctx.output.results[: self.k]]
        unexpected = [id for id in top_k if id not in self.expected]
        problems = [
            *([f"only {len(top_k)} results returned"] if len(top_k) < self.k else []),
            *([f"unexpected in top {self.k}: {unexpected}"] if unexpected else []),
        ]
        reason = "; ".join(problems) or None
        score = (len(top_k) - len(unexpected)) / self.k

        return {
            "Precision": EvaluationReason(value=score, reason=reason),
            "Precision passed": EvaluationReason(
                value=score >= self.threshold,
                reason=reason,
            ),
        }
