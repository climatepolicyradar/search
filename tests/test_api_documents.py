"""Tests for ``GET /search/documents/{document_id}``."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from search.data_in_models import Document
from search.engines import VespaError


@pytest.fixture
def document_client():
    """Provide a test client with the document engine mocked."""
    with patch("api.routers.DevVespaDocumentSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine
        yield TestClient(app), mock_engine


def test_get_document_returns_200_when_found(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.get.return_value = Document(
        id="doc-1",
        title="A Climate Document",
        description="About climate.",
    )

    response = client.get("/search/documents/doc-1")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "doc-1"
    mock_engine.get.assert_called_once_with("doc-1")


def test_get_document_returns_404_when_not_found(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.get.return_value = None

    response = client.get("/search/documents/missing-id")

    assert response.status_code == 404


def test_get_document_returns_503_on_vespa_error(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.get.side_effect = VespaError("Vespa is down")

    response = client.get("/search/documents/doc-1")

    assert response.status_code == 503
