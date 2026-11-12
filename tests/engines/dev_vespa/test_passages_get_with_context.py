"""Tests for fetching one passage with the passages either side of it."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest

from search.engines import ListResponse, VespaError
from search.engines.dev_vespa import DevVespaPassageSearchEngine
from search.passage import Passage


def engine_with(
    lookup: httpx2.Response, neighbours: list[Passage] | None = None
) -> tuple[DevVespaPassageSearchEngine, AsyncMock, list[httpx2.Request]]:
    """
    An engine whose docid lookup gets `lookup` and whose search gets `neighbours`.

    :return: The engine, its mocked search, and the lookup requests it sent
    """
    lookup_requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        lookup_requests.append(request)
        return lookup

    settings = MagicMock(vespa_endpoint="http://vespa", vespa_read_token=None)
    engine = DevVespaPassageSearchEngine(
        settings=settings,
        httpx=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    search = AsyncMock(
        return_value=ListResponse(
            results=neighbours or [],
            total_size=len(neighbours or []),
            next_page_token=None,
        )
    )
    engine._aexecute = search  # type: ignore[method-assign]
    return engine, search, lookup_requests


def found(idx: int) -> httpx2.Response:
    return httpx2.Response(200, json={"fields": {"document_id": "d", "idx": idx}})


def passage(idx: int) -> Passage:
    return Passage(text_block_id=f"d::{idx}", idx=idx, document_id="d", text="t")


def test_looks_up_the_passage_by_docid_then_fetches_neighbours_in_reading_order():
    neighbours = [passage(70), passage(71), passage(72)]
    engine, search, lookup_requests = engine_with(found(71), neighbours)

    result = asyncio.run(engine.aget_with_context("d::71", context=1))

    assert result == neighbours
    (lookup_request,) = lookup_requests
    assert lookup_request.url.raw_path.startswith(
        b"/document/v1/passages/passages/docid/d%3A%3A71?"
    )
    (search_call,) = search.await_args_list
    body = search_call.kwargs["request_body"]
    assert body["document_id"] == "d"
    assert "range(idx, 70, 72) order by idx asc" in body["yql"]
    assert body["hits"] == 3


def test_id_cannot_change_the_lookup_path():
    text_block_id = "../../documents/x"
    engine, _, lookup_requests = engine_with(
        found(1), [Passage(text_block_id=text_block_id, idx=1, document_id="d")]
    )

    asyncio.run(engine.aget_with_context(text_block_id, context=0))

    (lookup_request,) = lookup_requests
    assert lookup_request.url.raw_path.startswith(
        b"/document/v1/passages/passages/docid/..%2F..%2Fdocuments%2Fx?"
    )


def test_no_context_is_just_the_passage():
    engine, search, _ = engine_with(found(71), [passage(71)])

    assert asyncio.run(engine.aget_with_context("d::71", context=0)) == [passage(71)]
    (search_call,) = search.await_args_list
    body = search_call.kwargs["request_body"]
    assert "range(idx, 71, 71)" in body["yql"]


def test_missing_passage_is_none():
    engine, search, _ = engine_with(httpx2.Response(404))

    assert asyncio.run(engine.aget_with_context("nope::1", context=1)) is None
    search.assert_not_awaited()


@pytest.mark.parametrize(
    "lookup",
    [
        httpx2.Response(500, text="boom"),
        httpx2.Response(200, text="not json"),
        httpx2.Response(200, json={"fields": {}}),
    ],
)
def test_failed_lookup_raises(
    lookup: httpx2.Response,
):
    engine, _, _ = engine_with(lookup)

    with pytest.raises(VespaError):
        asyncio.run(engine.aget_with_context("d::71", context=1))


def test_context_without_the_passage_raises():
    engine, _, _ = engine_with(found(71), [passage(70), passage(72)])

    with pytest.raises(VespaError):
        asyncio.run(engine.aget_with_context("d::71", context=1))
