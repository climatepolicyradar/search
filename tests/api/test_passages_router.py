"""Tests for ``GET /search/passages``."""

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from search.engines import ListResponse
from search.passage import Passage


@pytest.fixture
def passages_client():
    """Provide a test client with the passage engine mocked."""
    with patch("api.routers.DevVespaPassageSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.last_debug_info = None
        mock_engine_cls.return_value = mock_engine
        yield TestClient(app), mock_engine


def _passage(text_block_id: str = "block-1") -> Passage:
    return Passage(text_block_id=text_block_id, document_id="doc-1")


def test_read_passages_with_query_only(passages_client) -> None:
    """A plain query request returns results and passes no filters."""
    client, mock_engine = passages_client
    mock_engine.search.return_value = ListResponse(
        results=[_passage()], total_size=1, next_page_token=None
    )

    response = client.get("/search/passages", params={"query": "toxic"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["results"][0]["text_block_id"] == "block-1"
    _, kwargs = mock_engine.search.call_args
    assert kwargs["query"] == "toxic"
    assert kwargs["filters_json_string"] is None


def test_read_passages_with_document_id_filter(passages_client) -> None:
    """A ``document_id`` filter is normalised and forwarded to the engine."""
    client, mock_engine = passages_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    filters = (
        '{"op": "or", "filters": ['
        '{"field": "document_id", "op": "contains", "value": "doc.1.2.3"}, '
        '{"field": "document_id", "op": "contains", "value": "doc.4.5.6"}'
        "]}"
    )
    response = client.get("/search/passages", params={"filters": filters})

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args
    assert kwargs["filters_json_string"] is not None
    assert "doc.1.2.3" in kwargs["filters_json_string"]
    assert "doc.4.5.6" in kwargs["filters_json_string"]


def test_read_passages_with_concept_filter(passages_client) -> None:
    """A ``concepts.value.id`` (topic) filter is forwarded to the engine."""
    client, mock_engine = passages_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    filters = (
        '{"op": "and", "filters": ['
        '{"field": "concepts.value.id", "op": "contains", "value": "concept_123"}'
        "]}"
    )
    response = client.get("/search/passages", params={"filters": filters})

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args
    assert "concept_123" in kwargs["filters_json_string"]


def test_read_passages_with_malformed_filters_returns_400(passages_client) -> None:
    """Malformed filter JSON is rejected with HTTP 400 before reaching the engine."""
    client, mock_engine = passages_client

    response = client.get("/search/passages", params={"filters": "not-json"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    mock_engine.search.assert_not_called()


def test_read_passages_default_order_by_is_idx_asc(passages_client) -> None:
    """Omitting ``order_by`` defaults to ascending idx order."""
    client, mock_engine = passages_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    response = client.get("/search/passages", params={"query": "toxic"})

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args
    order_by = kwargs["order_by"]
    assert len(order_by) == 1
    assert order_by[0].field == "idx"
    assert order_by[0].direction == "asc"


def test_read_passages_order_by_relevance(passages_client) -> None:
    """``order_by=relevance desc`` is parsed and forwarded to the engine."""
    client, mock_engine = passages_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    response = client.get(
        "/search/passages", params={"query": "toxic", "order_by": "relevance desc"}
    )

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args
    assert kwargs["order_by"][0].field == "relevance"


def test_read_passages_order_by_unsupported_field_returns_400(passages_client) -> None:
    """An unsupported ``order_by`` field is rejected with HTTP 400."""
    client, mock_engine = passages_client

    response = client.get(
        "/search/passages", params={"query": "toxic", "order_by": "title asc"}
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    mock_engine.search.assert_not_called()
