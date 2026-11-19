"""Tests for fetching one document by id."""

import asyncio
from unittest.mock import MagicMock

import httpx2
import pytest

from search.engines import VespaError
from search.engines.dev_vespa import DevVespaDocumentSearchEngine
from search.engines.vespa_query.client import Settings
from tests.http import MockHandler


def test_id_cannot_change_the_lookup_path():
    # The MCP passes a model-written id straight through, so it can contain "/".
    lookup_requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        lookup_requests.append(request)
        return httpx2.Response(404)

    engine = DevVespaDocumentSearchEngine(
        settings=MagicMock(vespa_endpoint="http://vespa", vespa_read_token=None),
        httpx=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )

    asyncio.run(engine.aget("../../passages/x?fieldSet=[all]"))

    (lookup_request,) = lookup_requests
    assert lookup_request.url.raw_path.startswith(
        b"/document/v1/documents/documents/docid/"
        b"..%2F..%2Fpassages%2Fx%3FfieldSet%3D%5Ball%5D?"
    )


def test_a_torn_down_connection_is_retried_once(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    """Vespa Cloud recycles connections on a timer; that is not a user-visible failure."""
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)
    handler.add_error(httpx2.RemoteProtocolError("goaway"))
    handler.add_text_response(404, "")

    assert asyncio.run(engine.aget("d_1")) is None
    assert handler.request_count == 2


def test_a_retry_that_also_fails_raises(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)
    handler.add_error(httpx2.RemoteProtocolError("goaway"))
    handler.add_error(httpx2.RemoteProtocolError("goaway"))

    with pytest.raises(VespaError):
        asyncio.run(engine.aget("d_1"))

    assert handler.request_count == 2


def test_a_refused_connection_is_not_retried(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    """Re-sending this would double the load on a Vespa that is already struggling."""
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)
    handler.add_error(httpx2.ConnectError("refused"))

    with pytest.raises(VespaError):
        asyncio.run(engine.aget("d_1"))

    assert handler.request_count == 1
