from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance.evaluators.evaluator import HasId, HasResults


@dataclass
class RanksAbove[I](Evaluator[I, HasResults[HasId], object]):
    higher: str
    lower: str
    k: int = 20

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasResults[HasId], object],
    ) -> dict[str, EvaluationReason]:
        """Check the higher ID is in the top k and the lower ID is absent or below it."""
        top_k = [result.id for result in ctx.output.results[: self.k]]
        higher_rank = top_k.index(self.higher) + 1 if self.higher in top_k else None
        lower_rank = top_k.index(self.lower) + 1 if self.lower in top_k else None
        reason = f"{self.higher} at {higher_rank}, {self.lower} at {lower_rank}"
        passed = higher_rank is not None and (
            lower_rank is None or higher_rank < lower_rank
        )

        return {
            "RanksAbove": EvaluationReason(value=float(passed), reason=reason),
            "RanksAbove passed": EvaluationReason(value=passed, reason=reason),
        }
