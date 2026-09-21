"""Tests for `GET /search/documents:download`."""

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from search.data_in_models import Document
from search.engines import ListResponse, VespaError


@pytest.fixture
def document_client():
    with patch("api.routers.DevVespaDocumentSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine
        yield TestClient(app), mock_engine


def test_download_returns_csv_with_content_disposition(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[
            Document(id="doc-1", title="A Climate Document", description=None)
        ],
        total_size=1,
        next_page_token=None,
    )

    response = client.get(
        "/search/documents:download", params={"query": "toxic"}
    )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "doc-1" in response.text


def test_download_defaults_max_results_to_500(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    client.get("/search/documents:download", params={"query": "toxic"})

    _, kwargs = mock_engine.search.call_args
    assert kwargs["pagination"].page_size == 100


def test_download_respects_max_results_query_param(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[Document(id=f"doc-{i}", title="t", description=None) for i in range(5)],
        total_size=5,
        next_page_token=None,
    )

    response = client.get(
        "/search/documents:download",
        params={"query": "toxic", "max_results": 5},
    )

    _, kwargs = mock_engine.search.call_args
    assert kwargs["pagination"].page_size == 5
    body_rows = response.text.strip().splitlines()[1:]
    assert len(body_rows) == 5


def test_download_returns_503_on_vespa_error(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.search.side_effect = VespaError("Vespa is down")

    response = client.get(
        "/search/documents:download", params={"query": "toxic"}
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"] == "Search service unavailable"


def test_download_rejects_non_positive_max_results(document_client) -> None:
    client, _ = document_client

    response = client.get(
        "/search/documents:download",
        params={"query": "toxic", "max_results": 0},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
