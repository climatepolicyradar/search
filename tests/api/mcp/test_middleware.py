import asyncio
import logging
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from api.mcp.filters import FilterArgError
from api.mcp.middleware import CallLogMiddleware, ErrorMessageMiddleware
from api.mcp.server import MAX_RESULTS, Limit
from search.engines import VespaError

LOGGER = "api.mcp.middleware"


def make_server() -> FastMCP:
    """A throwaway server with no Vespa, so the middleware is tested on its own."""
    mcp = FastMCP("test", mask_error_details=True)
    mcp.add_middleware(CallLogMiddleware())
    mcp.add_middleware(ErrorMessageMiddleware())

    @mcp.tool
    def fails(kind: str) -> list[str]:
        if kind == "vespa":
            raise VespaError("secret internals", status_code=503)
        if kind == "filter":
            raise FilterArgError("Use the ISO code")
        raise ValueError("secret bug")

    @mcp.tool
    def missing() -> list[str]:
        raise ToolError("No passage with that id")

    @mcp.tool
    def capped(limit: Limit = 10) -> int:
        return limit

    @mcp.tool
    def paged() -> dict[str, Any]:
        return {"results": ["a", "b", "c"], "has_more": True}

    return mcp


def call_log_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    # FastMCP logs failures itself too, so keep only our middleware's lines.
    return [record for record in caplog.records if record.name == LOGGER]


def call(name: str, args: dict[str, Any]) -> Any:
    async def run():
        async with Client(make_server()) as client:
            return await client.call_tool(name, args)

    return asyncio.run(run())


def test_vespa_error_gets_fixed_message():
    with pytest.raises(ToolError, match="Search is unavailable") as exc:
        call("fails", {"kind": "vespa"})
    assert "secret" not in str(exc.value)


def test_filter_arg_error_reaches_the_model():
    with pytest.raises(ToolError, match="Use the ISO code"):
        call("fails", {"kind": "filter"})


def test_unknown_error_stays_masked():
    with pytest.raises(ToolError) as exc:
        call("fails", {"kind": "bug"})
    assert "secret" not in str(exc.value)


def test_limit_at_max_is_accepted():
    assert call("capped", {"limit": MAX_RESULTS}).data == MAX_RESULTS


@pytest.mark.parametrize("limit", [0, MAX_RESULTS + 1])
def test_limit_outside_range_is_rejected(limit: int):
    with pytest.raises(ToolError):
        call("capped", {"limit": limit})


def test_successful_call_is_logged(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        call("capped", {"limit": 5})
    [record] = call_log_records(caplog)
    assert record.levelno == logging.INFO
    assert record.getMessage().startswith("Success: tool call surface=mcp tool=capped")


def test_failed_call_is_logged_as_error(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER), pytest.raises(ToolError):
        call("fails", {"kind": "vespa"})
    [record] = call_log_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("Error: tool call surface=mcp tool=fails")


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("fails", {"kind": "filter"}),
        ("missing", {}),
        ("capped", {"limit": MAX_RESULTS + 1}),
    ],
)
def test_caller_mistake_is_logged_as_rejected_not_error(
    caplog: pytest.LogCaptureFixture, tool: str, args: dict[str, Any]
):
    with caplog.at_level(logging.INFO, logger=LOGGER), pytest.raises(ToolError):
        call(tool, args)
    [record] = call_log_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage().startswith(
        f"Rejected: tool call surface=mcp tool={tool}"
    )


def test_unknown_error_is_logged_as_error(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER), pytest.raises(ToolError):
        call("fails", {"kind": "bug"})
    [record] = call_log_records(caplog)
    assert record.levelno == logging.ERROR


def test_failed_call_logs_the_original_error_not_the_model_message(
    caplog: pytest.LogCaptureFixture,
):
    with (
        caplog.at_level(logging.INFO, logger=LOGGER),
        pytest.raises(ToolError, match="Search is unavailable"),
    ):
        call("fails", {"kind": "vespa"})
    [record] = call_log_records(caplog)
    assert "error=VespaError('secret internals')" in record.getMessage()


def test_success_log_counts_results(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        call("paged", {})
    [record] = call_log_records(caplog)
    assert record.getMessage().endswith("results=3")
