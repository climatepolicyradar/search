"""Tests for fetching one document by id."""

import asyncio
from unittest.mock import MagicMock

import httpx2

from search.engines.dev_vespa import DevVespaDocumentSearchEngine


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
