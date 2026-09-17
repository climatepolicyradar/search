"""Tests for relevance tests."""

import json
import logging
from unittest.mock import MagicMock

import pytest

from relevance_tests import (
    RelevanceRunIncompleteError,
    TestResult,
    TestStatus,
    calculate_test_result_metrics,
    generate_test_run_id,
    run_tests_for_engine,
)
from relevance_tests.html_report import render_test_results_html
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine, VespaError
from search.identifiers import Identifier
from search.label import Label

pytest.fixture()


def get_mock_search_engine():
    class MockEngine:
        @property
        def name(self):
            return "JSONLabelSearchEngine"

    return MockEngine()


def test_generate_test_run_id_is_deterministic(
    simple_test_case, simple_test_result, test_labels
):
    """Test that generate_test_run_id produces the same ID for identical inputs."""

    engine = get_mock_search_engine()
    test_cases = [simple_test_case]
    test_results = [simple_test_result]

    id1 = generate_test_run_id(engine, test_cases, test_results)  # type: ignore
    id2 = generate_test_run_id(engine, test_cases, test_results)  # type: ignore

    assert id1 == id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


def test_generate_test_run_id_changes_when_test_case_changes(
    simple_test_case, another_test_case, simple_test_result
):
    """Test that generate_test_run_id produces different IDs when test cases change."""

    engine = get_mock_search_engine()

    test_results = [simple_test_result]

    id1 = generate_test_run_id(engine, [simple_test_case], test_results)  # type: ignore
    id2 = generate_test_run_id(engine, [another_test_case], test_results)  # type: ignore

    assert id1 != id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


def test_generate_test_run_id_changes_when_test_result_changes(
    simple_test_case, simple_test_result, test_labels
):
    """Test that generate_test_run_id produces different IDs when test results change."""

    engine = get_mock_search_engine()
    test_cases = [simple_test_case]

    id1 = generate_test_run_id(engine, test_cases, [simple_test_result])  # type: ignore

    modified_test_result = TestResult(
        test_case=simple_test_result.test_case,
        status="failed",  # Changed from passed to failed
        search_engine_id=simple_test_result.search_engine_id,
        search_results=simple_test_result.search_results,
    )
    id2 = generate_test_run_id(engine, test_cases, [modified_test_result])  # type: ignore

    assert id1 != id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


def test_generate_test_run_id_changes_when_engine_changes(
    simple_test_case, simple_test_result
):
    """Test that generate_test_run_id produces different IDs when the engine changes."""

    class FirstEngine:
        @property
        def name(self):
            return "MyFirstSearchEngine"

    class SecondEngine:
        @property
        def name(self):
            return "MySecondSearchEngine"

    first_engine = FirstEngine()
    second_engine = SecondEngine()

    test_cases = [simple_test_case]
    test_results = [simple_test_result]

    id1 = generate_test_run_id(first_engine, test_cases, test_results)  # type: ignore
    id2 = generate_test_run_id(second_engine, test_cases, test_results)  # type: ignore

    assert id1 != id2
    assert isinstance(id1, Identifier)
    assert isinstance(id2, Identifier)


# region Infrastructure failures are not relevance failures


def _result(
    simple_test_case, status: TestStatus, error: str | None = None
) -> TestResult:
    return TestResult(
        test_case=simple_test_case,
        status=status,
        error=error,
        search_engine_id=Identifier("abcd1234"),
        search_results=[],
    )


def test_an_infrastructure_failure_is_not_counted_as_a_relevance_failure(
    simple_test_case,
):
    """
    An errored case leaves the pass-rate denominator.

    A case that could not be evaluated carries no verdict about ranking, so
    scoring it as a failure under-reports the pass rate and makes a Vespa blip
    look like a regression (FUS-479).
    """
    results = [
        _result(simple_test_case, "passed"),
        _result(simple_test_case, "failed"),
        _result(simple_test_case, "errored", "VespaError: timed out"),
    ]

    overall = calculate_test_result_metrics(results)["overall"]

    assert overall["passed"] == 1
    assert overall["failed"] == 1
    assert overall["errored"] == 1
    assert overall["total"] == 3
    assert overall["pass_rate"] == 0.5


def test_an_all_errored_category_does_not_drag_the_macro_average(
    simple_test_case, another_test_case
):
    """A category with nothing evaluated has no pass rate to contribute."""
    simple_test_case.category = "evaluated"
    another_test_case.category = "all_errored"
    results = [
        _result(simple_test_case, "passed"),
        _result(another_test_case, "errored", "VespaError: timed out"),
    ]

    metrics = calculate_test_result_metrics(results)

    assert metrics["macro_average"]["pass_rate"] == 1.0


def test_an_errored_result_must_carry_an_error(simple_test_case):
    """The tagged status and the error message cannot disagree."""
    with pytest.raises(ValueError, match="error must be set if and only if"):
        _result(simple_test_case, "errored")

    with pytest.raises(ValueError, match="error must be set if and only if"):
        _result(simple_test_case, "failed", "VespaError: timed out")


def test_generate_test_run_id_differs_for_an_errored_and_a_failed_result(
    simple_test_case,
):
    """A run that could not evaluate a case is a different run."""
    engine = get_mock_search_engine()
    cases = [simple_test_case]

    failed = generate_test_run_id(engine, cases, [_result(simple_test_case, "failed")])  # type: ignore
    errored = generate_test_run_id(
        engine,  # type: ignore
        cases,
        [_result(simple_test_case, "errored", "VespaError: timed out")],
    )

    assert failed != errored


def test_the_html_report_shows_an_errored_badge(simple_test_case):
    """The report distinguishes the two, rather than showing both as FAIL."""
    html = render_test_results_html(
        test_results=[_result(simple_test_case, "errored", "VespaError: timed out")],
        engine_name="StubEngine",
        test_run_id="abcd1234",
    )

    assert "ERRORED" in html
    assert "VespaError: timed out" in html
    assert "Pass rate excludes errored cases" in html


# endregion Infrastructure failures are not relevance failures

# region The run loop


class StubEngine(SearchEngine[Label]):
    """An engine whose every search raises, or returns, whatever it was given."""

    model_class = Label

    def __init__(self, side_effects: list):
        self.side_effects = list(side_effects)
        self.calls = 0
        # The real engines expose this; the harness reads it per test case.
        self.last_debug_info: list[dict] | None = None

    @property
    def name(self) -> str:
        """The engine name, used in output filenames."""
        return "StubEngine"

    @property
    def id(self) -> Identifier:
        """A fixed id, so runs are comparable."""
        return Identifier("stub0000")

    def search(
        self,
        query: str,  # noqa: ARG002
        pagination: Pagination,  # noqa: ARG002
        order_by: list[OrderBy],  # noqa: ARG002
        filters_json_string: str | None = None,  # noqa: ARG002
    ) -> ListResponse[Label]:
        """Raise or return the next configured side effect."""
        self.calls += 1
        effect = self.side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return ListResponse(results=effect, total_size=len(effect), next_page_token=None)

    def count(self, query: str) -> int:  # noqa: ARG002
        """Unused by the harness."""
        return 0


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """Run the harness task body without Prefect, W&B, or the real output dir."""
    monkeypatch.setattr(
        "relevance_tests.get_run_logger", lambda: logging.getLogger("test-harness")
    )
    monkeypatch.setattr("search.config.TEST_RESULTS_DIR", tmp_path)
    monkeypatch.setattr("search.weights_and_biases.WandbSession", MagicMock())
    # The retry delay is not what these tests are about.
    monkeypatch.setattr("relevance_tests.VESPA_RETRY_DELAY_SECONDS", 0)
    return tmp_path


def _run(engine, test_cases) -> None:
    run_tests_for_engine.fn(engine, test_cases, Label, "labels")


def test_the_loop_tags_a_vespa_error_as_errored_and_still_writes_the_report(
    harness, simple_test_case
):
    """
    Raising must not cost us the report.

    The operator needs a red run *and* something to read: the artefacts are
    written before the run is failed.
    """
    engine = StubEngine([VespaError("Vespa request failed"), VespaError("again")])

    with pytest.raises(RelevanceRunIncompleteError):
        _run(engine, [simple_test_case])

    written = list(harness.glob("labels/*.jsonl"))
    assert len(written) == 1
    row = json.loads(written[0].read_text())
    assert row["status"] == "errored"
    assert "VespaError" in row["error"]
    assert list(harness.glob("labels/*.html"))


def test_a_transient_vespa_error_is_retried_once(harness, simple_test_case):
    """The failure this exists for is transient; one retry clears it."""
    engine = StubEngine([VespaError("Vespa request failed"), []])

    _run(engine, [simple_test_case])

    assert engine.calls == 2
    row = json.loads(next(harness.glob("labels/*.jsonl")).read_text())
    assert row["status"] in {"passed", "failed"}
    assert row["error"] is None


def test_a_test_case_bug_is_reported_rather_than_crashing_the_run(
    harness, simple_test_case
):
    """
    A non-Vespa exception is still "not evaluated", not a relevance failure.

    It is also not retried: nothing about it is transient.
    """
    engine = StubEngine([AttributeError("bad test case")])

    with pytest.raises(RelevanceRunIncompleteError):
        _run(engine, [simple_test_case])

    assert engine.calls == 1
    row = json.loads(next(harness.glob("labels/*.jsonl")).read_text())
    assert row["status"] == "errored"
    assert "AttributeError" in row["error"]


def test_a_clean_run_does_not_raise(harness, simple_test_case):
    """The counterpart: nothing errored, nothing raised."""
    engine = StubEngine([[]])

    _run(engine, [simple_test_case])

    assert engine.calls == 1


# endregion The run loop


def test_an_errored_result_carries_no_stale_debug_info(harness, simple_test_case):
    """
    Debug info from an earlier query is not attributed to a case that errored.

    `engine.last_debug_info` still holds the previous case's query, so copying
    it onto an errored result would show another query's ranking scores.
    """
    engine = StubEngine([[], VespaError("down"), VespaError("still down")])
    engine.last_debug_info = [{"relevance": 1.0}]

    with pytest.raises(RelevanceRunIncompleteError):
        _run(engine, [simple_test_case, simple_test_case])

    rows = [
        json.loads(line)
        for line in next(harness.glob("labels/*.jsonl")).read_text().splitlines()
    ]
    assert rows[0]["debug_info"] == [{"relevance": 1.0}]
    assert rows[1]["status"] == "errored"
    assert rows[1]["debug_info"] is None
