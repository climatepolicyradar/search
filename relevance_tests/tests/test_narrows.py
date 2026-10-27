import pytest
from pydantic_evals.evaluators import EvaluationReason

from relevance_tests.evaluators.narrows import Narrows
from relevance_tests.tests.fakes import Pair, Results, context


def pair(narrower: int | None, broader: int | None) -> Pair:
    return Pair(
        first=Results(total_size=narrower),
        second=Results(total_size=broader),
    )


@pytest.mark.parametrize(
    ("narrower", "broader", "passed"),
    [(5, 1000, True), (1000, 1000, True), (1001, 1000, False)],
)
def test_narrows(narrower: int, broader: int, passed: bool) -> None:
    outcome = Narrows().evaluate(context(pair(narrower=narrower, broader=broader)))
    assert outcome == {
        "Narrows passed": EvaluationReason(
            value=passed,
            reason=f"{narrower:,} hits vs 1,000 for the broader query",
        ),
    }


@pytest.mark.parametrize(("narrower", "broader"), [(None, 10), (5, None)])
def test_a_missing_hit_count_raises(narrower: int | None, broader: int | None) -> None:
    with pytest.raises(ValueError, match="no total hit count"):
        Narrows().evaluate(context(pair(narrower=narrower, broader=broader)))


def test_a_broader_query_matching_nothing_raises() -> None:
    with pytest.raises(ValueError, match="matched nothing"):
        Narrows().evaluate(context(pair(narrower=0, broader=0)))
