import pytest
from pydantic_evals.evaluators import EvaluationReason

from relevance_tests.evaluators.relative_order import RanksAbove
from relevance_tests.tests.fakes import context, results


@pytest.mark.parametrize(
    ("ids", "passed", "reason"),
    [
        (["h", "l"], True, "h at 1, l at 2"),
        (["l", "h"], False, "h at 2, l at 1"),
        (["h", "x"], True, "h at 1, l at None"),
        (["l", "x"], False, "h at None, l at 1"),
        (["x", "y"], False, "h at None, l at None"),
        (["h", "x", "l"], True, "h at 1, l at None"),
        (["x", "y", "h"], False, "h at None, l at None"),
    ],
    ids=[
        "higher above lower",
        "lower above higher",
        "lower absent",
        "higher absent",
        "both absent",
        "lower beyond k",
        "higher beyond k",
    ],
)
def test_ranks_above(ids: list[str], passed: bool, reason: str) -> None:
    outcome = RanksAbove(higher="h", lower="l", k=2).evaluate(context(results(*ids)))
    assert outcome == {
        "RanksAbove": EvaluationReason(value=float(passed), reason=reason),
        "RanksAbove passed": EvaluationReason(value=passed, reason=reason),
    }
