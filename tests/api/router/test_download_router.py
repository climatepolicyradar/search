"""Tests for `GET /search/documents:download`."""

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.download_templates import CSV_TEMPLATES
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
        results=[Document(id="doc-1", title="A Climate Document", description=None)],
        total_size=1,
        next_page_token=None,
    )

    response = client.get("/search/documents:download", params={"query": "toxic"})

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
        results=[
            Document(id=f"doc-{i}", title="t", description=None) for i in range(5)
        ],
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

    response = client.get("/search/documents:download", params={"query": "toxic"})

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["detail"] == "Search service unavailable"


def test_download_rejects_non_positive_max_results(document_client) -> None:
    client, _ = document_client

    response = client.get(
        "/search/documents:download",
        params={"query": "toxic", "max_results": 0},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize("template_name", sorted(CSV_TEMPLATES))
def test_download_applies_the_requested_template(
    document_client, template_name
) -> None:
    """`?template=` swaps the dynamic columns for that template's fixed ones."""
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[Document(id="doc-1", title="A Climate Document", description=None)],
        total_size=1,
        next_page_token=None,
    )

    response = client.get(
        "/search/documents:download",
        params={"query": "toxic", "template": template_name},
    )

    assert response.status_code == HTTPStatus.OK
    header = response.text.splitlines()[0]
    assert header.split(",") == list(CSV_TEMPLATES[template_name])


def test_download_without_a_template_keeps_the_dynamic_columns(
    document_client,
) -> None:
    """The default shape is unchanged - templating is strictly opt-in."""
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[Document(id="doc-1", title="A Climate Document", description=None)],
        total_size=1,
        next_page_token=None,
    )

    response = client.get("/search/documents:download", params={"query": "toxic"})

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[0].split(",") == [
        "document_id",
        "title",
        "description",
    ]


def test_download_rejects_an_unknown_template(document_client) -> None:
    """
    An unsupported template is a 422, not a silent fall back to the default.

    Returning the dynamic format under a name the caller asked for would hand
    them a different shape than they requested without saying so.
    """
    client, _ = document_client

    response = client.get(
        "/search/documents:download",
        params={"query": "toxic", "template": "not-a-template"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
