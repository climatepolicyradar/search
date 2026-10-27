from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from relevance_tests.evaluators.evaluator import HasSearchPair, HasTotalSize


@dataclass
class Narrows[I](Evaluator[I, HasSearchPair[HasTotalSize], object]):
    def evaluate(
        self,
        ctx: EvaluatorContext[I, HasSearchPair[HasTotalSize], object],
    ) -> dict[str, EvaluationReason]:
        """Check the first query matches no more hits than the broader second query."""
        narrower = ctx.output.first.total_size
        broader = ctx.output.second.total_size
        if narrower is None or broader is None:
            raise ValueError("search gave no total hit count")
        # 0 <= 0 would pass without testing anything
        if broader == 0:
            raise ValueError("the broader query matched nothing")
        reason = f"{narrower:,} hits vs {broader:,} for the broader query"

        return {
            "Narrows passed": EvaluationReason(
                value=narrower <= broader,
                reason=reason,
            ),
        }
