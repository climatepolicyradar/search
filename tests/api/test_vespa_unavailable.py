"""
Tests that a Vespa failure is surfaced rather than swallowed.

The distinction these pin down is 503 ("we could not answer you") versus
200-with-no-results ("we answered you: nothing matched"). A client that cannot
tell those apart will render a broken backend as a legitimately empty search.

The same applies one layer up, to the request-lifecycle log: an error response
logged as a success hides the outage from whoever is on call.
"""

import logging
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from search.engines import ListResponse, VespaError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def document_engine():
    """Mock the document engine used by ``/documents`` and ``/documents/{id}``."""
    with patch("api.routers.DevVespaDocumentSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.last_debug_info = None
        mock_engine_cls.return_value = mock_engine
        yield mock_engine


@pytest.fixture
def passage_engine():
    with patch("api.routers.DevVespaPassageSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.last_debug_info = None
        mock_engine_cls.return_value = mock_engine
        yield mock_engine


@pytest.fixture
def label_engine():
    with patch("api.routers.DevVespaLabelSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.last_debug_info = None
        mock_engine_cls.return_value = mock_engine
        yield mock_engine


def _assert_unavailable(response) -> None:
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    # The Vespa error text can contain the upstream response body, so the
    # client gets a fixed message rather than the exception detail.
    assert response.json()["detail"] == "Search service unavailable"


def test_get_document_returns_503(client, document_engine) -> None:
    document_engine.get.side_effect = VespaError("Vespa is down")

    _assert_unavailable(client.get("/search/documents/doc-1"))


def test_search_documents_returns_503(client, document_engine) -> None:
    document_engine.search.side_effect = VespaError("Vespa is down")

    _assert_unavailable(client.get("/search/documents", params={"query": "toxic"}))


def test_search_documents_returns_503_when_only_aggregations_fail(
    client, document_engine
) -> None:
    """Search and aggregations are fanned out together; either failing is a 503."""
    document_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )
    document_engine.aggregations.side_effect = VespaError("Vespa is down")

    _assert_unavailable(client.get("/search/documents", params={"query": "toxic"}))


def test_search_documents_returns_503_when_only_facets_fail(
    client, document_engine
) -> None:
    document_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )
    document_engine.aggregations.return_value = []
    document_engine.labels_value_type_facets.side_effect = VespaError("Vespa is down")

    _assert_unavailable(
        client.get(
            "/search/documents",
            params={"query": "toxic", "fields": "facets.labels.value.type"},
        )
    )


def test_search_passages_returns_503(client, passage_engine) -> None:
    passage_engine.search.side_effect = VespaError("Vespa is down")

    _assert_unavailable(client.get("/search/passages", params={"query": "toxic"}))


def test_search_labels_returns_503(client, label_engine) -> None:
    label_engine.search.side_effect = VespaError("Vespa is down")

    _assert_unavailable(client.get("/search/labels", params={"query": "toxic"}))


def test_a_503_is_not_logged_as_a_success(client, document_engine, caplog) -> None:
    """
    The request-lifecycle log must not call a handled error a success.

    A 503 logged at INFO as "Success: Request completed" is invisible to log
    grepping and error alerting - the same blind spot, one layer up, as
    answering a failed query with a 200.
    """
    document_engine.search.side_effect = VespaError("Vespa is down")

    with caplog.at_level(logging.INFO, logger="api.main"):
        client.get("/search/documents", params={"query": "toxic"})

    lifecycle_logs = [
        record for record in caplog.records if "Request completed" in record.message
    ]
    assert len(lifecycle_logs) == 1
    assert lifecycle_logs[0].levelno == logging.ERROR
    assert lifecycle_logs[0].getMessage().startswith("Error: Request completed")


def test_a_400_is_logged_as_rejected_not_as_an_error(client, caplog) -> None:
    """
    A client's bad request warns: neither a success nor our failure.

    WARNING keeps it filterable without putting caller mistakes in the same
    bucket as an outage - a burst of 400s is usually a caller bug worth seeing.
    """
    with caplog.at_level(logging.INFO, logger="api.main"):
        response = client.get("/search/passages", params={"filters": "not-json"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    lifecycle_logs = [
        record for record in caplog.records if "Request completed" in record.message
    ]
    assert len(lifecycle_logs) == 1
    assert lifecycle_logs[0].levelno == logging.WARNING
    assert lifecycle_logs[0].getMessage().startswith("Rejected: Request completed")


def test_a_200_is_still_logged_as_a_success(client, document_engine, caplog) -> None:
    document_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )
    document_engine.aggregations.return_value = []

    with caplog.at_level(logging.INFO, logger="api.main"):
        response = client.get("/search/documents", params={"query": "toxic"})

    assert response.status_code == HTTPStatus.OK
    lifecycle_logs = [
        record for record in caplog.records if "Request completed" in record.message
    ]
    assert len(lifecycle_logs) == 1
    assert lifecycle_logs[0].levelno == logging.INFO
    assert lifecycle_logs[0].getMessage().startswith("Success: Request completed")


def test_no_matches_is_still_a_200(client, document_engine) -> None:
    """The counterpart to the above: an empty result set is a successful answer."""
    document_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )
    document_engine.aggregations.return_value = []

    response = client.get("/search/documents", params={"query": "no-such-thing"})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["results"] == []
    assert body["total_size"] == 0
