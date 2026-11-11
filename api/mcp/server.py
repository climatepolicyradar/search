"""
The search MCP: five read-only tools over the same engines as the REST API.

Each tool checks its args, builds a filter, calls one engine method and trims
the result.
"""

from collections.abc import Iterable
from datetime import date
from typing import Annotated

import httpx2
import mcp_types
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.server import LifespanCallable
from pydantic import Field

from api.mcp import descriptions
from api.mcp.filters import (
    Category,
    FilterArgError,
    Region,
    ResponseArea,
    build_filter,
)
from api.mcp.middleware import CallLogMiddleware, ErrorMessageMiddleware
from api.mcp.models import (
    DocumentDetail,
    DocumentHit,
    DocumentResults,
    PassageHit,
    PassageInContext,
    PassageResults,
    TopicHit,
    TopicResults,
    dedupe_passages,
    title_id,
    worth_quoting,
)
from api.settings import settings
from api.state import HttpxDep
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
)
from search.engines.vespa_query.filters import FieldFilter, Filter
from search.passage import Passage

DEFAULT_LIMIT = 10
MAX_RESULTS = 25
# Capped in the schema, so the model sees the max up front instead of being
# cut off silently.
Limit = Annotated[int, Field(ge=1, le=MAX_RESULTS)]
# Passages are fetched with headroom, so dropping repeats and headings still
# leaves `limit` results.
PASSAGE_OVERFETCH = 2
MAX_CONTEXT_PASSAGES = 3
BY_RELEVANCE = [OrderBy(field="relevance", direction="desc")]

READ_ONLY = mcp_types.ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, open_world_hint=False
)


async def document_titles(
    passages: Iterable[Passage], httpx: httpx2.AsyncClient
) -> dict[str, str]:
    """
    Titles for the documents these passages come from, in one query.

    Passages don't carry a title, and without one the model needs an extra
    call per document just to say what it's quoting.
    """
    ids = list(dict.fromkeys(title_id(passage) for passage in passages))
    if not ids:
        return {}
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=httpx)
    results = await engine.asearch(
        query=None,
        pagination=Pagination(page_token=1, page_size=len(ids)),
        order_by=[],
        filters=Filter(
            op="or",
            filters=[
                FieldFilter(field="id", op="contains", value=document_id)
                for document_id in ids
            ],
        ),
    )
    return {document.id: document.title for document in results.results}


def build_server(lifespan: LifespanCallable) -> FastMCP:
    """
    Build the search MCP.

    :param lifespan: Yields the app's `State`, which tools read with `HttpxDep`.
    """
    mcp = FastMCP(
        "cpr-search",
        instructions=descriptions.INSTRUCTIONS,
        mask_error_details=True,
        lifespan=lifespan,
    )
    # The first one added is the outermost, so the log sees the final message.
    mcp.add_middleware(CallLogMiddleware())
    mcp.add_middleware(ErrorMessageMiddleware())

    @mcp.tool(description=descriptions.SEARCH_DOCUMENTS, annotations=READ_ONLY)
    async def search_documents(
        httpx: HttpxDep,
        query: Annotated[str, Field(description=descriptions.QUERY)],
        geographies: Annotated[
            list[str] | None, Field(description=descriptions.GEOGRAPHIES)
        ] = None,
        regions: Annotated[
            list[Region] | None, Field(description=descriptions.REGIONS)
        ] = None,
        categories: Annotated[
            list[Category] | None, Field(description=descriptions.CATEGORIES)
        ] = None,
        response_areas: Annotated[
            list[ResponseArea] | None, Field(description=descriptions.RESPONSE_AREAS)
        ] = None,
        topics: Annotated[
            list[str] | None, Field(description=descriptions.TOPICS)
        ] = None,
        published_after: Annotated[
            date | None, Field(description=descriptions.PUBLISHED_AFTER)
        ] = None,
        published_before: Annotated[
            date | None, Field(description=descriptions.PUBLISHED_BEFORE)
        ] = None,
        limit: Annotated[Limit, Field(description=descriptions.LIMIT)] = DEFAULT_LIMIT,
    ) -> DocumentResults:
        engine = DevVespaDocumentSearchEngine(settings=settings, httpx=httpx)
        results = await engine.asearch(
            query=query,
            pagination=Pagination(page_token=1, page_size=limit),
            order_by=BY_RELEVANCE,
            filters=build_filter(
                geographies=geographies,
                regions=regions,
                categories=categories,
                response_areas=response_areas,
                topics=topics,
                published_after=published_after,
                published_before=published_before,
                principals_only=True,
            ),
        )
        return DocumentResults(
            results=[
                DocumentHit.from_document(document) for document in results.results
            ],
            has_more=(
                results.total_size > limit
                if results.total_size is not None
                else len(results.results) >= limit
            ),
        )

    @mcp.tool(description=descriptions.SEARCH_PASSAGES, annotations=READ_ONLY)
    async def search_passages(
        httpx: HttpxDep,
        query: Annotated[str, Field(description=descriptions.QUERY)],
        document_ids: Annotated[
            list[str] | None, Field(description=descriptions.DOCUMENT_IDS)
        ] = None,
        geographies: Annotated[
            list[str] | None, Field(description=descriptions.GEOGRAPHIES)
        ] = None,
        regions: Annotated[
            list[Region] | None, Field(description=descriptions.REGIONS)
        ] = None,
        categories: Annotated[
            list[Category] | None, Field(description=descriptions.CATEGORIES)
        ] = None,
        topics: Annotated[
            list[str] | None, Field(description=descriptions.TOPICS)
        ] = None,
        limit: Annotated[Limit, Field(description=descriptions.LIMIT)] = DEFAULT_LIMIT,
    ) -> PassageResults:
        engine = DevVespaPassageSearchEngine(settings=settings, httpx=httpx)
        pagination = Pagination(page_token=1, page_size=limit * PASSAGE_OVERFETCH)
        if document_ids:
            # `asearch_within` ORs filters with the query, so label filters
            # would widen the search. Raise so the model knows they weren't applied.
            if geographies or regions or categories or topics:
                raise FilterArgError(
                    "document_ids can't be combined with geographies, regions, "
                    "categories or topics. The documents are already chosen, "
                    "so search within them using just the query."
                )
            results = await engine.asearch_within(
                document_ids=document_ids,
                query=query,
                pagination=pagination,
                order_by=BY_RELEVANCE,
            )
        else:
            results = await engine.asearch(
                query=query,
                pagination=pagination,
                order_by=BY_RELEVANCE,
                filters=build_filter(
                    geographies=geographies,
                    regions=regions,
                    categories=categories,
                    topics=topics,
                    for_passages=True,
                ),
            )
        quotable = [passage for passage in results.results if worth_quoting(passage)]
        kept = dedupe_passages(quotable)
        titles = await document_titles(kept[:limit], httpx)
        return PassageResults(
            results=[
                PassageHit.from_passage(passage, titles) for passage in kept[:limit]
            ],
            has_more=len(kept) > limit or len(results.results) >= pagination.page_size,
        )

    @mcp.tool(description=descriptions.GET_PASSAGE, annotations=READ_ONLY)
    async def get_passage(
        httpx: HttpxDep,
        text_block_id: Annotated[str, Field(description=descriptions.TEXT_BLOCK_ID)],
        context: Annotated[
            int, Field(ge=0, le=MAX_CONTEXT_PASSAGES, description=descriptions.CONTEXT)
        ] = 1,
    ) -> PassageInContext:
        engine = DevVespaPassageSearchEngine(settings=settings, httpx=httpx)
        passages = await engine.aget_with_context(text_block_id, context)
        if passages is None:
            raise ToolError(
                f"No passage with id {text_block_id!r}. "
                "Use a text_block_id from search_passages."
            )
        # The engine guarantees the passage is in its own context.
        position = next(
            index
            for index, passage in enumerate(passages)
            if passage.text_block_id == text_block_id
        )
        titles = await document_titles(passages[position : position + 1], httpx)
        hits = [
            PassageHit.from_passage(passage, titles, max_chars=None)
            for passage in passages
        ]
        return PassageInContext(
            passage=hits[position],
            before=hits[:position],
            after=hits[position + 1 :],
        )

    @mcp.tool(description=descriptions.GET_DOCUMENT, annotations=READ_ONLY)
    async def get_document(
        httpx: HttpxDep,
        document_id: Annotated[str, Field(description=descriptions.DOCUMENT_ID)],
    ) -> DocumentDetail:
        engine = DevVespaDocumentSearchEngine(settings=settings, httpx=httpx)
        document = await engine.aget(document_id)
        if document is None:
            raise ToolError(
                f"No document with id {document_id!r}. "
                "Use search_documents to find a document's id."
            )
        return DocumentDetail.from_document(document)

    @mcp.tool(description=descriptions.SEARCH_TOPICS, annotations=READ_ONLY)
    async def search_topics(
        httpx: HttpxDep,
        query: Annotated[str, Field(description=descriptions.TOPIC_QUERY)],
        limit: Annotated[
            Limit, Field(description=descriptions.TOPIC_LIMIT)
        ] = DEFAULT_LIMIT,
    ) -> TopicResults:
        engine = DevVespaLabelSearchEngine(settings=settings, httpx=httpx)
        results = await engine.asearch(
            query=query,
            pagination=Pagination(page_token=1, page_size=limit),
            order_by=[],
            label_type="concept",
        )
        return TopicResults(
            results=[TopicHit.from_label(label) for label in results.results]
        )

    return mcp
