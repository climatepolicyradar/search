from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance.evaluators.evaluator import HasId, HasResults, HasSearchPair


@dataclass
class Overlap[I](Evaluator[I, HasSearchPair[HasResults[HasId]], object]):
    k: int = 20
    threshold: float = 1.0

    def get_default_evaluation_name(self) -> str:
        """Name the metric after the cutoff it scores."""
        return f"overlap@{self.k}"

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasSearchPair[HasResults[HasId]], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of the two top k lists that overlap."""
        first = [result.id for result in ctx.output.first.results[: self.k]]
        second = [result.id for result in ctx.output.second.results[: self.k]]
        overlapping = len(set(first) & set(second))
        comparable = min(len(first), len(second))
        score = overlapping / comparable if comparable else 0.0
        only_first = [first_id for first_id in first if first_id not in second]
        only_second = [second_id for second_id in second if second_id not in first]
        reason = (
            f"{overlapping}/{comparable} overlap; "
            f"only in first: {only_first}; only in second: {only_second}"
        )

        name = self.get_default_evaluation_name()
        return {
            name: EvaluationReason(value=score, reason=reason),
            f"{name} passed": EvaluationReason(
                value=score >= self.threshold,
                reason=reason,
            ),
        }
