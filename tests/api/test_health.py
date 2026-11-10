import logging
from http import HTTPStatus

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.health import Probe
from api.health import probes as probes_dep
from api.main import HEALTH_ROUTE_PATH
from search.engines import VespaError

PASS = None
FAIL = VespaError("probe failed", status_code=HTTPStatus.SERVICE_UNAVAILABLE)


def build_probes(outcomes: dict[str, Exception | None]) -> dict[str, Probe]:
    """One probe per entry, raising where asked."""

    def build(failure: Exception | None) -> Probe:
        async def probe() -> None:
            if failure is not None:
                raise failure

        return probe

    return {name: build(failure) for name, failure in outcomes.items()}


def run_health(
    app: FastAPI,
    test_client: TestClient,
    outcomes: dict[str, Exception | None],
) -> httpx2.Response:
    """Run `read_health` with one probe per entry, failing where asked."""
    app.dependency_overrides[probes_dep] = lambda: build_probes(outcomes)
    try:
        return test_client.get(HEALTH_ROUTE_PATH)
    finally:
        del app.dependency_overrides[probes_dep]


def run_one_probe(
    app: FastAPI,
    test_client: TestClient,
    name: str,
    outcomes: dict[str, Exception | None],
) -> httpx2.Response:
    """Run `read_probe` for `name` against the probes described by `outcomes`."""
    app.dependency_overrides[probes_dep] = lambda: build_probes(outcomes)
    try:
        return test_client.get(f"{HEALTH_ROUTE_PATH}/probes/{name}")
    finally:
        del app.dependency_overrides[probes_dep]


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
    app: FastAPI,
    test_client: TestClient,
    outcomes: dict[str, Exception | None],
    expected_status: str,
    expected_code: HTTPStatus,
) -> None:
    response = run_health(app, test_client, outcomes)

    assert response.json()["status"] == expected_status
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
def test_a_probe_may_raise_anything_without_taking_the_endpoint_down(
    app: FastAPI,
    test_client: TestClient,
    failure: Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        response = run_health(app, test_client, {"a": failure, "b": PASS})

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert [
        (probe["name"], probe["healthy"]) for probe in response.json()["probes"]
    ] == [
        ("a", False),
        ("b", True),
    ]


def test_every_probe_is_reported_once_in_order(app: FastAPI, test_client: TestClient) -> None:
    response = run_health(app, test_client, {"a": PASS, "b": FAIL, "c": PASS})

    assert [
        (probe["name"], probe["healthy"]) for probe in response.json()["probes"]
    ] == [
        ("a", True),
        ("b", False),
        ("c", True),
    ]


def test_an_earlier_healthy_run_does_not_mask_a_later_failure(
    app: FastAPI,
    test_client: TestClient,
) -> None:
    """
    The answer comes from the current probes, never from what came before.

    A 503 has to be reproducible from current state alone, or nobody can work
    out why a task was replaced.
    """
    run_health(app, test_client, {"a": PASS})

    response = run_health(app, test_client, {"a": FAIL})

    assert response.json()["status"] == "unhealthy"
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
def test_one_probe_answers_only_for_itself(
    app: FastAPI,
    test_client: TestClient,
    outcomes: dict[str, Exception | None],
    expected_healthy: bool,
    expected_code: HTTPStatus,
) -> None:
    """
    The whole point of a route per probe: one red dependency, one red check.

    If a sibling could colour this answer, the uptime series would be five
    copies of `/health` rather than five independent ones.
    """
    response = run_one_probe(app, test_client, "a", outcomes)

    assert (response.json()["name"], response.json()["healthy"]) == (
        "a",
        expected_healthy,
    )
    assert response.status_code == expected_code


def test_an_unknown_probe_is_a_404_not_a_failed_probe(app: FastAPI, test_client: TestClient) -> None:
    """
    A name we don't have is absent, not unhealthy.

    A 503 here would tell a synthetic check that a dependency is down when what
    is actually wrong is the URL pointed at it.
    """
    response = run_one_probe(app, test_client, "nope", {"a": PASS})

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "nope" in response.json()["detail"]
