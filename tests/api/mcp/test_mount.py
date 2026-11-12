"""
The MCP is only mounted on the search API when MCP_ENABLED is set.

It's read once at import, so each case runs `api.main` in a fresh process.
"""

import os
import subprocess
import sys
import textwrap

INITIALIZE = textwrap.dedent(
    """
    import logging

    from fastapi.testclient import TestClient
    from api.main import app, logger

    lifecycle_lines = []
    handler = logging.Handler()
    handler.emit = lambda record: lifecycle_lines.append(record.getMessage())
    logger.addHandler(handler)

    with TestClient(app) as client:
        response = client.post(
            "/search/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        print(response.status_code)
    print(sum("Request completed" in line for line in lifecycle_lines))
    """
)


def initialize(mcp_enabled: str) -> tuple[int, int]:
    """The initialize call's status, and how many lifecycle lines it logged."""
    result = subprocess.run(
        [sys.executable, "-c", INITIALIZE],
        env={**os.environ, "MCP_ENABLED": mcp_enabled},
        capture_output=True,
        text=True,
        check=True,
    )
    *_, status, lifecycle_line_count = result.stdout.strip().splitlines()
    return int(status), int(lifecycle_line_count)


def test_mcp_is_not_mounted_by_default():
    # The search API is public, so the MCP stays off until sign in exists.
    status, _ = initialize("false")
    assert status == 404


def test_mcp_answers_when_enabled():
    status, _ = initialize("true")
    assert status == 200


def test_mcp_calls_skip_the_request_lifecycle_log():
    _, lifecycle_line_count = initialize("true")
    assert lifecycle_line_count == 0
