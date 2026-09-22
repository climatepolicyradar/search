"""Unit tests for the daily feeder's sequencing and failure handling."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import nightly_flow
import pytest
from nightly_flow import FeedRunFailed, nightly_feeder_flow, run_feed_deployment
from prefect.client.schemas.objects import State
from prefect.states import Completed, Failed, Running
from prefect.testing.utilities import prefect_test_harness


@pytest.fixture(autouse=True, scope="module")
def prefect_db():
    """Give tasks and flows a backend to record runs against."""
    with prefect_test_harness():
        yield


@dataclass
class _StubFlowRun:
    """The two attributes run_feed_deployment reads off run_deployment's return."""

    state: State | None
    id: UUID = field(default_factory=uuid4)


@dataclass
class _StubRunDeployment:
    """Stands in for run_deployment, recording the deployments it was asked for."""

    state: State | None = field(default_factory=Completed)
    calls: list[str] = field(default_factory=list)

    def __call__(self, name: str, **_kwargs: Any) -> _StubFlowRun:
        self.calls.append(name)
        return _StubFlowRun(state=self.state)


def test_run_feed_deployment_returns_the_flow_run_when_the_feed_completes(
    monkeypatch,
) -> None:
    stub = _StubRunDeployment(state=Completed())
    monkeypatch.setattr(nightly_flow, "run_deployment", stub)

    flow_run = run_feed_deployment(
        name="search-vespa-feeder-labels/search-vespa-feeder-labels"
    )

    assert stub.calls == ["search-vespa-feeder-labels/search-vespa-feeder-labels"]
    assert flow_run.state is not None and flow_run.state.is_completed()


def test_run_feed_deployment_raises_when_the_feed_fails(monkeypatch) -> None:
    monkeypatch.setattr(nightly_flow, "run_deployment", _StubRunDeployment(Failed()))

    with pytest.raises(FeedRunFailed, match="Failed"):
        run_feed_deployment(
            name="search-vespa-feeder-documents/search-vespa-feeder-documents"
        )


def test_run_feed_deployment_raises_when_the_feed_is_still_running_at_the_timeout(
    monkeypatch,
) -> None:
    """A timed-out feed comes back non-terminal, which must not read as success."""
    monkeypatch.setattr(nightly_flow, "run_deployment", _StubRunDeployment(Running()))

    with pytest.raises(FeedRunFailed, match="Running"):
        run_feed_deployment(
            name="search-vespa-feeder-passages/search-vespa-feeder-passages"
        )


def test_feeds_run_in_order_documents_labels_passages(monkeypatch) -> None:
    stub = _StubRunDeployment(state=Completed())
    monkeypatch.setattr(nightly_flow, "run_deployment", stub)

    nightly_feeder_flow()

    assert stub.calls == [
        "search-vespa-feeder-documents/search-vespa-feeder-documents",
        "search-vespa-feeder-labels/search-vespa-feeder-labels",
        "search-vespa-feeder-passages/search-vespa-feeder-passages",
    ]


def test_a_failed_feed_stops_the_chain(monkeypatch) -> None:
    """Passages must not end up feeding on top of a broken documents run."""
    stub = _StubRunDeployment(state=Failed())
    monkeypatch.setattr(nightly_flow, "run_deployment", stub)

    with pytest.raises(FeedRunFailed):
        nightly_feeder_flow()

    assert stub.calls == ["search-vespa-feeder-documents/search-vespa-feeder-documents"]
