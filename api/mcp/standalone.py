"""
Run the search MCP on its own, for local development.

    uv run python -m api.mcp.standalone

Serves streamable HTTP on http://127.0.0.1:8001/mcp. Not stdio: importing
`api.settings` logs to stdout, which would corrupt a stdio stream.
Sign in is off here, the deployed MCP is mounted in `api/main.py` instead.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastmcp import FastMCP

from api.mcp.server import build_server

PORT = 8001


class _SharedClient:
    """Holds the one HTTP client this process opens, once the lifespan starts."""

    def __init__(self) -> None:
        self._client: httpx2.AsyncClient | None = None

    def __call__(self) -> httpx2.AsyncClient:
        if self._client is None:
            raise RuntimeError("The MCP lifespan has not started")
        return self._client

    @asynccontextmanager
    async def lifespan(self, _server: FastMCP) -> AsyncIterator[dict]:
        async with httpx2.AsyncClient(http2=True) as client:
            self._client = client
            yield {}
            self._client = None


_shared_client = _SharedClient()
mcp = build_server(httpx=_shared_client, lifespan=_shared_client.lifespan)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=PORT)
