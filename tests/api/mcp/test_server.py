"""
Tests for the search MCP's tools, through FastMCP's in-memory client.

The engines are mocked: these pin down what each tool sends to its engine and
what reaches the model, not search quality.
"""

import asyncio
import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from api.mcp.server import build_server, document_titles
from search.engines import ListResponse, VespaError
from search.label import LabelSearchResult
from search.passage import Passage
from tests.api.mcp.test_models import make_document

EXPECTED_TOOLS = {
    "search_documents",
    "search_passages",
    "get_document",
    "find_concepts",
    "get_passage",
}


def make_passage(**overrides) -> Passage:
    fields = {
        "text_block_id": "p_1_b_1",
        "document_id": "CCLW.document.1.0",
        "principal_id": "CCLW.family.1.0",
        "text": "The Act sets a target for adaptation finance.",
        "pages": [1],
    }
    return Passage(**(fields | overrides))


@pytest.fixture
def document_engine() -> Iterator[MagicMock]:
    with patch("api.mcp.server.DevVespaDocumentSearchEngine") as engine_cls:
        engine = MagicMock()
        engine.asearch = AsyncMock(
            return_value=ListResponse(
                results=[make_document()], total_size=1, next_page_token=None
            )
        )
        engine.aget = AsyncMock(return_value=make_document())
        engine_cls.return_value = engine
        yield engine


TITLES = {"CCLW.family.1.0": "Climate Change Act"}


@pytest.fixture
def passage_engine() -> Iterator[MagicMock]:
    # The title lookup is patched here, so it doesn't reach the document
    # engine and mix its calls up with search_documents'.
    with (
        patch("api.mcp.server.DevVespaPassageSearchEngine") as engine_cls,
        patch("api.mcp.server.document_titles", AsyncMock(return_value=TITLES)),
    ):
        engine = MagicMock()
        response = ListResponse(
            results=[make_passage()], total_size=1, next_page_token=None
        )
        engine.asearch = AsyncMock(return_value=response)
        engine.asearch_within = AsyncMock(return_value=response)
        engine_cls.return_value = engine
        yield engine


@pytest.fixture
def label_engine() -> Iterator[MagicMock]:
    with patch("api.mcp.server.DevVespaLabelSearchEngine") as engine_cls:
        engine = MagicMock()
        concept = LabelSearchResult(
            id="concept::Q1343",
            type="concept",
            value="adaptation finance",
            alternative_labels=["climate adaptation funding"],
        )
        engine.asearch = AsyncMock(
            return_value=ListResponse(
                results=[concept], total_size=1, next_page_token=None
            )
        )
        engine_cls.return_value = engine
        yield engine


def call(tool: str, arguments: dict):
    async def run():
        async with Client(build_server(httpx=MagicMock)) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def list_tools():
    async def run():
        async with Client(build_server(httpx=MagicMock)) as client:
            return await client.list_tools()

    return asyncio.run(run())


def test_exposes_exactly_the_five_tools():
    # Tool names are a contract with every connected client: renaming one
    # should be a deliberate change to this test.
    assert {tool.name for tool in list_tools()} == EXPECTED_TOOLS


def test_every_tool_is_read_only():
    for tool in list_tools():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


def test_search_documents_returns_trimmed_hits(document_engine: MagicMock):
    result = call("search_documents", {"query": "adaptation"})

    assert result.structured_content is not None
    (hit,) = result.structured_content["results"]
    assert hit["id"] == "CCLW.document.1.0"
    assert "labels" not in hit


def test_search_documents_sends_limit_order_and_filters(document_engine: MagicMock):
    call(
        "search_documents", {"query": "adaptation", "geographies": ["KEN"], "limit": 5}
    )

    kwargs = document_engine.asearch.await_args.kwargs
    assert kwargs["query"] == "adaptation"
    assert kwargs["pagination"].page_size == 5
    assert [(order.field, order.direction) for order in kwargs["order_by"]] == [
        ("relevance", "desc")
    ]
    assert kwargs["filters"] is not None


def test_search_passages_without_documents_uses_search(passage_engine: MagicMock):
    call("search_passages", {"query": "adaptation", "categories": ["Law"]})

    passage_engine.asearch.assert_awaited_once()
    passage_engine.asearch_within.assert_not_awaited()
    assert (
        "category::category::Law::Law"
        in passage_engine.asearch.await_args.kwargs["filters"].model_dump_json()
    )


def test_search_passages_with_documents_searches_within(passage_engine: MagicMock):
    call(
        "search_passages",
        {"query": "adaptation", "document_ids": ["CCLW.document.1.0"]},
    )

    passage_engine.asearch.assert_not_awaited()
    kwargs = passage_engine.asearch_within.await_args.kwargs
    assert kwargs["document_ids"] == ["CCLW.document.1.0"]
    assert "filters" not in kwargs


def test_document_ids_with_filters_is_refused_not_silently_dropped(
    passage_engine: MagicMock,
):
    with pytest.raises(ToolError, match="can't be combined"):
        call(
            "search_passages",
            {
                "query": "adaptation",
                "document_ids": ["CCLW.document.1.0"],
                "geographies": ["KEN"],
            },
        )
    passage_engine.asearch_within.assert_not_awaited()


def test_get_document_returns_one_hit(document_engine: MagicMock):
    result = call("get_document", {"document_id": "CCLW.document.1.0"})

    assert result.structured_content is not None
    assert result.structured_content["id"] == "CCLW.document.1.0"
    assert result.structured_content["is_principal"] is False


def test_missing_document_raises(document_engine: MagicMock):
    document_engine.aget.return_value = None

    with pytest.raises(ToolError, match="No document with id") as exc:
        call("get_document", {"document_id": "missing"})

    assert "search_documents" in str(exc.value)


def test_limit_over_the_cap_is_rejected(document_engine: MagicMock):
    with pytest.raises(ToolError):
        call("search_documents", {"query": "adaptation", "limit": 26})
    document_engine.asearch.assert_not_awaited()


def test_unknown_topic_is_rejected(document_engine: MagicMock):
    with pytest.raises(ToolError):
        call("search_documents", {"query": "flooding", "topics": ["Floods"]})
    document_engine.asearch.assert_not_awaited()


def test_unknown_category_is_rejected(document_engine: MagicMock):
    with pytest.raises(ToolError):
        call("search_documents", {"query": "adaptation", "categories": ["Blog"]})


def vespa_error(status_code: int | None, cause: BaseException | None) -> VespaError:
    exc = VespaError("secret upstream detail", status_code=status_code)
    exc.__cause__ = cause
    return exc


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (vespa_error(429, None), "busy right now. Wait a few seconds"),
        (vespa_error(503, None), "unavailable right now. Try again shortly"),
        (
            vespa_error(None, httpx2.ConnectError("refused")),
            "unavailable right now. Try again shortly",
        ),
        (vespa_error(504, None), "timed out. Try again with a shorter query"),
        (vespa_error(400, None), "Don't retry the same call"),
        (vespa_error(500, None), "Retrying won't help"),
        (vespa_error(None, ValueError("bad json")), "Retrying won't help"),
    ],
    ids=["throttled", "down", "unreachable", "timeout", "bad-query", "500", "bad-json"],
)
def test_vespa_errors_only_suggest_retrying_when_it_could_help(
    document_engine: MagicMock, error: VespaError, message: str
):
    document_engine.asearch.side_effect = error

    with pytest.raises(ToolError) as exc:
        call("search_documents", {"query": "adaptation"})

    assert message in str(exc.value)
    assert "secret upstream detail" not in str(exc.value)


def test_find_concepts_searches_concept_labels(label_engine: MagicMock):
    result = call("find_concepts", {"query": "adaptation finance"})

    assert label_engine.asearch.await_args.kwargs["label_type"] == "concept"
    assert result.structured_content is not None
    (hit,) = result.structured_content["results"]
    assert hit == {
        "id": "concept::Q1343",
        "name": "adaptation finance",
        "alternative_names": ["climate adaptation funding"],
    }


def test_concepts_reach_both_search_engines(
    document_engine: MagicMock, passage_engine: MagicMock
):
    call("search_documents", {"query": "adaptation", "concepts": ["Q1343"]})
    call("search_passages", {"query": "adaptation", "concepts": ["Q1343"]})

    for engine in (document_engine, passage_engine):
        filters = engine.asearch.await_args.kwargs["filters"]
        assert "concept::Q1343" in filters.model_dump_json()


def test_bad_filter_arg_tells_the_model_how_to_fix_it(document_engine: MagicMock):
    with pytest.raises(ToolError, match="find_concepts"):
        call("search_documents", {"query": "adaptation", "concepts": ["adaptation"]})
    document_engine.asearch.assert_not_awaited()


def test_call_log_records_successes_without_caplog_lowering_the_level():
    # caplog.at_level would hide this: the logger must be at INFO on its own,
    # or every Success line is dropped in the running service.
    build_server(httpx=MagicMock)

    assert logging.getLogger("api.mcp.middleware").isEnabledFor(logging.INFO)


def test_search_documents_returns_one_result_per_law(document_engine: MagicMock):
    call("search_documents", {"query": "adaptation"})

    filters = document_engine.asearch.await_args.kwargs["filters"]
    assert "status::Principal" in filters.model_dump_json()


def test_search_passages_drops_repeats_across_versions(passage_engine: MagicMock):
    same_text = "The Act sets a target for adaptation finance."
    passage_engine.asearch.return_value = ListResponse(
        results=[
            make_passage(text_block_id="v1::1", document_id="v1", text=same_text),
            make_passage(text_block_id="v2::1", document_id="v2", text=same_text),
            make_passage(text_block_id="v1::2", document_id="v1", text="Other text."),
        ],
        total_size=3,
        next_page_token=None,
    )

    result = call("search_passages", {"query": "adaptation", "limit": 2})

    assert passage_engine.asearch.await_args.kwargs["pagination"].page_size == 4
    assert result.structured_content is not None
    assert [hit["text_block_id"] for hit in result.structured_content["results"]] == [
        "v1::1",
        "v1::2",
    ]


def test_search_passages_drops_repeats_across_documents(passage_engine: MagicMock):
    # e.g. the same paragraph in two of a country's UN submissions.
    same_text = "Kenya will mobilise adaptation finance."
    passage_engine.asearch.return_value = ListResponse(
        results=[
            make_passage(text_block_id="a::1", principal_id="ndc.1", text=same_text),
            make_passage(text_block_id="b::1", principal_id="ndc.2", text=same_text),
        ],
        total_size=2,
        next_page_token=None,
    )

    result = call("search_passages", {"query": "adaptation"})

    assert result.structured_content is not None
    assert len(result.structured_content["results"]) == 1


def test_search_passages_drops_headings_and_page_furniture(
    passage_engine: MagicMock,
):
    passage_engine.asearch.return_value = ListResponse(
        results=[
            make_passage(text_block_id="h", looks_like_short_heading=True),
            make_passage(text_block_id="f", is_page_header_or_footer=True),
            make_passage(text_block_id="toc", looks_like_table_of_contents=True),
            make_passage(text_block_id="ref", looks_like_reference_list=True),
            make_passage(text_block_id="body"),
        ],
        total_size=5,
        next_page_token=None,
    )

    result = call("search_passages", {"query": "carbon budgets"})

    assert result.structured_content is not None
    assert [hit["text_block_id"] for hit in result.structured_content["results"]] == [
        "body"
    ]


def test_full_page_of_documents_says_there_are_more(document_engine: MagicMock):
    document_engine.asearch.return_value = ListResponse(
        results=[make_document(id=f"doc.{number}") for number in range(2)],
        total_size=None,
        next_page_token=None,
    )

    full = call("search_documents", {"query": "climate law", "limit": 2})
    partial = call("search_documents", {"query": "climate law", "limit": 3})

    assert full.structured_content is not None
    assert partial.structured_content is not None
    assert full.structured_content["has_more"] is True
    assert partial.structured_content["has_more"] is False


@pytest.mark.parametrize(("total_size", "has_more"), [(2, False), (3, True)])
def test_documents_has_more_uses_the_total_when_known(
    document_engine: MagicMock, total_size: int, has_more: bool
):
    document_engine.asearch.return_value = ListResponse(
        results=[make_document(id=f"doc.{number}") for number in range(2)],
        total_size=total_size,
        next_page_token=None,
    )

    result = call("search_documents", {"query": "climate law", "limit": 2})

    assert result.structured_content is not None
    assert result.structured_content["has_more"] is has_more


def test_get_passage_returns_full_text_with_neighbours(passage_engine: MagicMock):
    long_text = "s.25 Climate Change Fund. " * 100
    passage_engine.aget_with_context = AsyncMock(
        return_value=[
            make_passage(text_block_id="d::70", text="Before."),
            make_passage(text_block_id="d::71", text=long_text),
            make_passage(text_block_id="d::72", text="After."),
        ]
    )

    result = call("get_passage", {"text_block_id": "d::71"})

    passage_engine.aget_with_context.assert_awaited_once_with("d::71", 1)
    assert result.structured_content is not None
    content = result.structured_content
    assert content["passage"]["text_block_id"] == "d::71"
    assert content["passage"]["text"] == long_text
    assert content["passage"]["text_truncated"] is False
    assert [passage["text_block_id"] for passage in content["before"]] == ["d::70"]
    assert [passage["text_block_id"] for passage in content["after"]] == ["d::72"]


def test_get_passage_at_the_start_of_a_document(passage_engine: MagicMock):
    passage_engine.aget_with_context = AsyncMock(
        return_value=[
            make_passage(text_block_id="d::0", text="First."),
            make_passage(text_block_id="d::1", text="Second."),
        ]
    )

    result = call("get_passage", {"text_block_id": "d::0"})

    assert result.structured_content is not None
    assert result.structured_content["before"] == []
    assert result.structured_content["passage"]["text_block_id"] == "d::0"


def test_passages_carry_their_document_title(passage_engine: MagicMock):
    result = call("search_passages", {"query": "adaptation"})

    assert result.structured_content is not None
    (hit,) = result.structured_content["results"]
    assert hit["document_title"] == "Climate Change Act"
    assert "language" not in hit


def test_document_titles_are_looked_up_once_by_principal(
    document_engine: MagicMock,
):
    titles = asyncio.run(
        document_titles(
            [
                make_passage(text_block_id="v1::1", document_id="v1"),
                make_passage(text_block_id="v2::1", document_id="v2"),
                make_passage(principal_id=None, document_id="CCLW.document.9.0"),
            ],
            httpx=MagicMock(),
        )
    )

    document_engine.asearch.assert_awaited_once()
    kwargs = document_engine.asearch.await_args.kwargs
    ids = [condition.value for condition in kwargs["filters"].filters]
    assert ids == ["CCLW.family.1.0", "CCLW.document.9.0"]
    assert kwargs["pagination"].page_size == 2
    assert titles == {"CCLW.document.1.0": "Climate Change Act"}


def test_no_passages_need_no_title_lookup(document_engine: MagicMock):
    assert asyncio.run(document_titles([], httpx=MagicMock())) == {}
    document_engine.asearch.assert_not_awaited()


def test_document_title_lookup_failure_surfaces(document_engine: MagicMock):
    document_engine.asearch.side_effect = VespaError("down", status_code=503)

    with pytest.raises(VespaError):
        asyncio.run(document_titles([make_passage()], httpx=MagicMock()))


def test_missing_passage_raises(passage_engine: MagicMock):
    passage_engine.aget_with_context = AsyncMock(return_value=None)

    with pytest.raises(ToolError, match="No passage with id"):
        call("get_passage", {"text_block_id": "nope::1"})


def test_get_passage_context_is_capped(passage_engine: MagicMock):
    passage_engine.aget_with_context = AsyncMock(return_value=[])

    with pytest.raises(ToolError):
        call("get_passage", {"text_block_id": "d::71", "context": 4})
    passage_engine.aget_with_context.assert_not_awaited()


def test_regions_reach_both_search_engines(
    document_engine: MagicMock, passage_engine: MagicMock
):
    call("search_documents", {"query": "floods", "regions": ["Sub-Saharan Africa"]})
    call("search_passages", {"query": "floods", "regions": ["Sub-Saharan Africa"]})

    for engine in (document_engine, passage_engine):
        filters = engine.asearch.await_args.kwargs["filters"]
        assert "region::SSF" in filters.model_dump_json()


def test_search_passages_has_no_topics_filter():
    # Topics are on a law's Principal, which passages can't see, so the filter
    # would quietly match almost nothing.
    tools = {tool.name: tool for tool in list_tools()}

    assert "topics" in tools["search_documents"].input_schema["properties"]
    assert "topics" not in tools["search_passages"].input_schema["properties"]


def passages(count: int) -> ListResponse:
    return ListResponse(
        results=[
            make_passage(text_block_id=f"d::{number}", text=f"Passage {number}.")
            for number in range(count)
        ],
        total_size=count,
        next_page_token=None,
    )


@pytest.mark.parametrize(
    ("returned", "limit", "has_more"),
    [
        (2, 2, False),  # fewer than a full overfetched page, none left over
        (3, 2, True),  # more unique passages than the limit
        (4, 2, True),  # a full overfetched page, so Vespa may have more
        (1, 2, False),
    ],
)
def test_passages_has_more(
    passage_engine: MagicMock, returned: int, limit: int, has_more: bool
):
    passage_engine.asearch.return_value = passages(returned)

    result = call("search_passages", {"query": "adaptation", "limit": limit})

    assert result.structured_content is not None
    assert result.structured_content["has_more"] is has_more
    assert len(result.structured_content["results"]) == min(returned, limit)


def test_get_passage_with_no_context(passage_engine: MagicMock):
    passage_engine.aget_with_context = AsyncMock(return_value=[make_passage()])

    call("get_passage", {"text_block_id": "p_1_b_1", "context": 0})

    passage_engine.aget_with_context.assert_awaited_once_with("p_1_b_1", 0)


@pytest.mark.parametrize(
    "label_filter",
    [
        {"geographies": ["KEN"]},
        {"regions": ["Sub-Saharan Africa"]},
        {"categories": ["Law"]},
        {"concepts": ["Q1343"]},
    ],
)
def test_document_ids_with_any_label_filter_is_refused(
    passage_engine: MagicMock, label_filter: dict
):
    with pytest.raises(ToolError, match="can't be combined"):
        call(
            "search_passages",
            {"query": "adaptation", "document_ids": ["d"], **label_filter},
        )
    passage_engine.asearch_within.assert_not_awaited()


def test_impossible_date_range_reaches_the_model(document_engine: MagicMock):
    with pytest.raises(ToolError, match="Swap them"):
        call(
            "search_documents",
            {
                "query": "net zero",
                "published_after": "2024-01-01",
                "published_before": "2020-01-01",
            },
        )
    document_engine.asearch.assert_not_awaited()
