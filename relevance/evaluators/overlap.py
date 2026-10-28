from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance.evaluators.evaluator import HasId, HasResults, HasSearchPair


@dataclass
class Overlap[I](Evaluator[I, HasSearchPair[HasResults[HasId]], object]):
    k: int = 20
    threshold: float = 1.0
    strict_order: bool = False

    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasSearchPair[HasResults[HasId]], object],
    ) -> dict[str, EvaluationReason]:
        """Score the share of the two top k lists that overlap."""
        first = [result.id for result in ctx.output.first.results[: self.k]]
        second = [result.id for result in ctx.output.second.results[: self.k]]
        if self.strict_order:
            overlapping = sum(1 for a, b in zip(first, second) if a == b)
        else:
            overlapping = len(set(first) & set(second))
        comparable = min(len(first), len(second))
        score = overlapping / comparable if comparable else 0.0
        only_first = [id for id in first if id not in second]
        only_second = [id for id in second if id not in first]
        reason = (
            f"{overlapping}/{comparable} overlap; "
            f"only in first: {only_first}; only in second: {only_second}"
        )

        return {
            "Overlap": EvaluationReason(value=score, reason=reason),
            "Overlap passed": EvaluationReason(
                value=score >= self.threshold,
                reason=reason,
            ),
        }
