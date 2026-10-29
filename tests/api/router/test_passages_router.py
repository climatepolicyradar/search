"""Tests for ``GET /search/passages``."""

import base64
import zlib
from collections.abc import Generator
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.filters import _NOT_DEFLATED
from api.main import app
from api.utils import passages_engine
from search.engines import ListResponse, OrderBy
from search.engines.dev_vespa import FieldFilter, Filter
from search.passage import Passage

type PassagesClient = tuple[TestClient, MagicMock]


@pytest.fixture
def passages_client() -> Generator[PassagesClient]:
    """Provide a test client with the passage engine replaced by a fake."""
    mock_engine = MagicMock()
    mock_engine.last_debug_info = None
    app.dependency_overrides[passages_engine] = lambda: mock_engine
    yield TestClient(app), mock_engine
    del app.dependency_overrides[passages_engine]


def _passage(text_block_id: str = "block-1") -> Passage:
    return Passage(text_block_id=text_block_id, document_id="doc-1")


def test_read_passages_with_query_only(passages_client: PassagesClient) -> None:
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
    assert kwargs["filters"] is None


def test_read_passages_with_document_id_filter(passages_client: PassagesClient) -> None:
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
    assert kwargs["filters"] == Filter(
        op="or",
        filters=[
            FieldFilter(field="document_id", op="contains", value="doc.1.2.3"),
            FieldFilter(field="document_id", op="contains", value="doc.4.5.6"),
        ],
    )


def test_read_passages_with_label_filter(passages_client: PassagesClient) -> None:
    """A ``labels.value.id`` filter is forwarded to the engine."""
    client, mock_engine = passages_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    filters = (
        '{"op": "and", "filters": ['
        '{"field": "labels.value.id", "op": "contains", "value": "concept::finance flow"}'
        "]}"
    )
    response = client.get("/search/passages", params={"filters": filters})

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args
    assert kwargs["filters"] == Filter(
        op="and",
        filters=[
            FieldFilter(
                field="labels.value.id", op="contains", value="concept::finance flow"
            )
        ],
    )


def test_read_passages_with_malformed_filters_returns_400(
    passages_client: PassagesClient,
) -> None:
    """Malformed filter JSON is rejected with HTTP 400 before reaching the engine."""
    client, mock_engine = passages_client

    response = client.get("/search/passages", params={"filters": "not-json"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    mock_engine.search.assert_not_called()


def test_read_passages_with_empty_filters_returns_400(
    passages_client: PassagesClient,
) -> None:
    """An empty ``filters`` value is malformed, not a request for no filters."""
    client, mock_engine = passages_client

    response = client.get("/search/passages", params={"filters": ""})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    mock_engine.search.assert_not_called()


_DOCUMENT_ID_FILTER = Filter(
    op="and",
    filters=[FieldFilter(field="document_id", op="contains", value="doc.1.2.3")],
)


def _deflate(data: bytes, *, pad: bool = False) -> str:
    """Encode as the browser's ``CompressionStream("deflate-raw")`` + base64url."""
    compressor = zlib.compressobj(wbits=-15)
    encoded = base64.urlsafe_b64encode(compressor.compress(data) + compressor.flush())
    return (encoded if pad else encoded.rstrip(b"=")).decode()


@pytest.mark.parametrize("pad", [False, True])
def test_read_passages_with_deflated_filters(
    passages_client: PassagesClient,
    pad: bool
) -> None:
    client, mock_engine = passages_client

    mock_engine.search.return_value = ListResponse(
        results=[],
        total_size=0,
        next_page_token=None
    )

    response = client.get(
        url="/search/passages",
        params={
            "filters": _deflate(_DOCUMENT_ID_FILTER.model_dump_json().encode(), pad=pad),
            "encoding": "deflate",
        },
    )

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args
    assert kwargs["filters"] == _DOCUMENT_ID_FILTER


@pytest.mark.parametrize(
    "filters",
    [
        pytest.param(_DOCUMENT_ID_FILTER.model_dump_json(), id="plain-json"),
        pytest.param("!!!", id="not-base64"),
        pytest.param(_deflate(b'{"op": "and", "filters": []}')[:-4], id="truncated"),
        pytest.param(_deflate(b"\xff\xfe"), id="not-utf8"),
        pytest.param(_deflate(b" " * 2 * 1024 * 1024), id="too-big"),
    ],
)
def test_read_passages_with_bad_deflated_filters_returns_400(
    passages_client: PassagesClient,
    filters: str
) -> None:
    client, mock_engine = passages_client

    response = client.get(
        params={"filters": filters, "encoding": "deflate"},
        url="/search/passages",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["detail"] == _NOT_DEFLATED
    mock_engine.search.assert_not_called()


def test_read_passages_default_order_by_is_idx_asc(
    passages_client: PassagesClient,
) -> None:
    client, mock_engine = passages_client

    mock_engine.search.return_value = ListResponse(
        next_page_token=None,
        total_size=0,
        results=[],
    )

    response = client.get(
        url="/search/passages",
        params={"query": "toxic"}
    )

    assert response.status_code == HTTPStatus.OK
    _, kwargs = mock_engine.search.call_args

    assert kwargs["order_by"] == [OrderBy(field="idx", direction="asc")]


def test_read_passages_order_by_relevance(passages_client: PassagesClient) -> None:
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
    assert kwargs["order_by"] == [OrderBy(field="relevance", direction="desc")]


def test_read_passages_order_by_unsupported_field_returns_400(
    passages_client: PassagesClient,
) -> None:
    client, mock_engine = passages_client

    response = client.get(
        "/search/passages", params={"query": "toxic", "order_by": "title asc"}
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    mock_engine.search.assert_not_called()


def test_read_passages_with_invalid_rank_returns_422() -> None:
    client = TestClient(app)

    response = client.get(
        "/search/passages", params={"query": "toxic", "rank_profile": "bogus"}
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
