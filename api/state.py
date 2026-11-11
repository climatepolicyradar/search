from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from typing import Annotated, TypedDict, cast

import httpx2
from fastapi import Depends as ApiDepends
from fastapi import Request
from fastmcp.dependencies import Depends as McpDepends
from fastmcp.server.dependencies import get_context


class State(TypedDict):
    httpx: httpx2.AsyncClient


@asynccontextmanager
async def build_state() -> AsyncGenerator[State]:
    async with httpx2.AsyncClient(http2=True) as client:
        yield State(httpx=client)


def _api_state(request: Request) -> State:
    return cast(State, request.app.state.shared)


def _mcp_state() -> State:
    return cast(State, get_context().lifespan_context)


# Each framework reads only its own `Depends`, so one type serves routes and tools.
StateDep = Annotated[
    State,
    ApiDepends(_api_state),
    McpDepends(_mcp_state),
]

def httpx(state: StateDep) -> httpx2.AsyncClient:
    """Retrieve the shared http client from app state"""
    return state["httpx"]


def _httpx_for_mcp(
    state: StateDep,
) -> AbstractAsyncContextManager[httpx2.AsyncClient]:
    # FastMCP would open and close the client itself, so wrap it to keep it shared.
    return nullcontext(state["httpx"])


HttpxDep = Annotated[
    httpx2.AsyncClient,
    ApiDepends(httpx),
    McpDepends(_httpx_for_mcp),
]
