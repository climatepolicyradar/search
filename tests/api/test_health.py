from http import HTTPStatus
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Response

from api import health
from search.engines import VespaError

PASS = None
FAIL = VespaError("probe failed", status_code=HTTPStatus.SERVICE_UNAVAILABLE)


def build_probes(outcomes: dict) -> dict:
    """One probe per entry, raising where asked."""

    def build(failure):
        def probe() -> None:
            if failure is not None:
                raise failure

        return probe

    return {name: build(failure) for name, failure in outcomes.items()}


def run_health(outcomes: dict) -> tuple:
    """Run `read_health` with one probe per entry, failing where asked."""
    # The logger is silenced, not asserted on: a failing probe logging its own
    # exception belongs to `run_probe`.
    with (
        patch.object(health, "logger"),
        patch.dict(health.PROBES, build_probes(outcomes), clear=True),
    ):
        response = Response()
        return health.read_health(response), response


def run_one_probe(name: str, outcomes: dict) -> tuple:
    """Run `read_probe` for `name` against the probes described by `outcomes`."""
    with (
        patch.object(health, "logger"),
        patch.dict(health.PROBES, build_probes(outcomes), clear=True),
    ):
        response = Response()
        return health.read_probe(name, response), response


@pytest.mark.parametrize(
    ("outcomes", "expected_status", "expected_code"),
    [
        ({"a": PASS}, "healthy", HTTPStatus.OK),
        ({"a": PASS, "b": PASS}, "healthy", HTTPStatus.OK),
        ({"a": FAIL}, "unhealthy", HTTPStatus.SERVICE_UNAVAILABLE),
        ({"a": PASS, "b": FAIL}, "unhealthy", HTTPStatus.SERVICE_UNAVAILABLE),
        ({"a": FAIL, "b": PASS}, "unhealthy", HTTPStatus.SERVICE_UNAVAILABLE),
        ({"a": FAIL, "b": FAIL}, "unhealthy", HTTPStatus.SERVICE_UNAVAILABLE),
    ],
    ids=["one-pass", "all-pass", "one-fail", "last-fails", "first-fails", "all-fail"],
)
def test_one_failing_probe_makes_the_whole_check_unhealthy(
    outcomes, expected_status, expected_code
):
    result, response = run_health(outcomes)

    assert result.status == expected_status
    assert response.status_code == expected_code


@pytest.mark.parametrize(
    "failure",
    [
        VespaError("no response", status_code=None),
        VespaError("refused", status_code=HTTPStatus.BAD_REQUEST),
        ValueError("boom"),
        RuntimeError("boom"),
        TimeoutError("boom"),
    ],
    ids=["vespa-no-status", "vespa-400", "value-error", "runtime-error", "timeout"],
)
def test_a_probe_may_raise_anything_without_taking_the_endpoint_down(failure):
    result, response = run_health({"a": failure, "b": PASS})

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert [(probe.name, probe.healthy) for probe in result.probes] == [
        ("a", False),
        ("b", True),
    ]


def test_every_probe_is_reported_once_in_order():
    result, _ = run_health({"a": PASS, "b": FAIL, "c": PASS})

    assert [(probe.name, probe.healthy) for probe in result.probes] == [
        ("a", True),
        ("b", False),
        ("c", True),
    ]


def test_an_earlier_healthy_run_does_not_mask_a_later_failure():
    """
    The answer comes from the current probes, never from what came before.

    A 503 has to be reproducible from current state alone, or nobody can work
    out why a task was replaced.
    """
    run_health({"a": PASS})

    result, response = run_health({"a": FAIL})

    assert result.status == "unhealthy"
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


@pytest.mark.parametrize(
    ("outcomes", "expected_healthy", "expected_code"),
    [
        ({"a": PASS}, True, HTTPStatus.OK),
        ({"a": FAIL}, False, HTTPStatus.SERVICE_UNAVAILABLE),
        ({"a": PASS, "b": FAIL}, True, HTTPStatus.OK),
        ({"a": FAIL, "b": PASS}, False, HTTPStatus.SERVICE_UNAVAILABLE),
    ],
    ids=["pass", "fail", "sibling-fails", "sibling-passes"],
)
def test_one_probe_answers_only_for_itself(outcomes, expected_healthy, expected_code):
    """
    The whole point of a route per probe: one red dependency, one red check.

    If a sibling could colour this answer, the uptime series would be five
    copies of `/health` rather than five independent ones.
    """
    result, response = run_one_probe("a", outcomes)

    assert (result.name, result.healthy) == ("a", expected_healthy)
    assert response.status_code == expected_code


def test_an_unknown_probe_is_a_404_not_a_failed_probe():
    """
    A name we don't have is absent, not unhealthy.

    A 503 here would tell a synthetic check that a dependency is down when what
    is actually wrong is the URL pointed at it.
    """
    with pytest.raises(HTTPException) as caught:
        run_one_probe("nope", {"a": PASS})

    assert caught.value.status_code == HTTPStatus.NOT_FOUND
    assert "nope" in caught.value.detail
