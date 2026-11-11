"""
A real tool call through the mounted app, with only Vespa mocked.

The other MCP tests patch the engines, so they can't catch the wiring between
the lifespan, the shared `State` and the engine deps, or the ranking the
engines are built with.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import MCP_PATH, build_mcp, create_app
from api.settings import settings
from search.engines.dev_vespa.passages_search_engine import (
    DEFAULT_PASSAGE_RANK_PROFILE,
)
from tests.http import MockHandler
from tests.state import stub_state


@pytest.fixture
def mcp_client(
    http_client: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(settings, "mcp_enabled", True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with (
            stub_state(httpx=http_client) as state,
            build_mcp(app=app, state=state),
        ):
            app.state.deps = state
            yield

    return TestClient(create_app(lifespan=lifespan))


def call_tool(client: TestClient, tool: str, arguments: dict) -> dict:
    response = client.post(
        f"{MCP_PATH}/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 200, response.text
    # Streamable HTTP answers as server-sent events.
    (data,) = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    return json.loads(data)


def test_tool_call_reaches_vespa_through_the_shared_client_with_rest_ranking(
    mcp_client: TestClient, handler: MockHandler
):
    handler.add_response({"root": {"children": []}})

    with mcp_client as client:
        message = call_tool(client, "search_passages", {"query": "adaptation"})

    assert message["result"]["isError"] is False
    assert message["result"]["structuredContent"]["results"] == []
    assert handler.last_json()["ranking.profile"] == DEFAULT_PASSAGE_RANK_PROFILE
