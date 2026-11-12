"""
The search MCP's middleware.

One log line per call, and fixed messages for known failures. Errors and
logging live here, so no tool catches anything.
"""

from time import perf_counter

import httpx2
import mcp_types as mt
from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

from api.mcp.filters import FilterArgError
from search.engines import VespaError
from search.log import get_logger

logger = get_logger(__name__)


class CallLogMiddleware(Middleware):
    """
    Log one line per tool call with its outcome and latency.

    Uses the same `Success:` / `Rejected:` / `Error:` prefixes and levels as
    `log_request_lifecycle` in `api/main.py`, so one grep covers both surfaces.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Log the call at a level matching its outcome."""
        start = perf_counter()
        log_args = (context.message.name, context.message.arguments)
        try:
            result = await call_next(context)
        except Exception as exc:
            rejected = _is_caller_mistake(exc)
            (logger.warning if rejected else logger.error)(
                "%s: tool call surface=mcp tool=%s args=%r duration_ms=%s error=%r",
                "Rejected" if rejected else "Error",
                *log_args,
                _elapsed_ms(start),
                exc.__cause__ or exc,
            )
            raise
        logger.info(
            "Success: tool call surface=mcp tool=%s args=%r duration_ms=%s results=%s",
            *log_args,
            _elapsed_ms(start),
            _result_count(result),
        )
        return result


class ErrorMessageMiddleware(Middleware):
    """
    Give the model a fixed, actionable message for known failures.

    FastMCP wraps whatever a tool raises in a ToolError before middleware sees
    it, so the original exception is on `__cause__`. Anything else stays masked.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Swap a known failure's message for one the model can act on."""
        try:
            return await call_next(context)
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, VespaError):
                raise ToolError(vespa_error_message(cause)) from cause
            if isinstance(cause, FilterArgError):
                raise ToolError(str(cause)) from cause
            raise


def vespa_error_message(exc: VespaError) -> str:
    """
    A fixed message for a failed search, so no Vespa detail reaches the model.

    Only says to retry when retrying could help. The real error is in the call
    log and the Vespa client's log.
    """
    status = exc.status_code
    if status == 429:
        return "Search is busy right now. Wait a few seconds and try again."
    if status == 504:
        return "The search timed out. Try again with a shorter query or fewer filters."
    if status is not None and 400 <= status < 500:
        return (
            "Search couldn't run this query. Don't retry the same call. Try "
            "different wording or fewer filters."
        )
    if status in (502, 503) or isinstance(exc.__cause__, httpx2.TransportError):
        return "Search is unavailable right now. Try again shortly."
    return (
        "Search hit an internal error. Retrying won't help, so tell the user "
        "search isn't working right now."
    )


def _is_caller_mistake(exc: Exception) -> bool:
    """
    True when the model's call was wrong, the MCP's equivalent of a 4xx.

    Args that fail the tool schema arrive as a bare `ValidationError`. A
    `ToolError` a tool raised itself (e.g. no such id) has no cause, whereas
    FastMCP sets the cause when it wraps anything else.
    """
    if isinstance(exc, ValidationError):
        return True
    return isinstance(exc, ToolError) and (
        exc.__cause__ is None or isinstance(exc.__cause__, FilterArgError)
    )


def _elapsed_ms(start: float) -> int:
    return round((perf_counter() - start) * 1000)


def _result_count(result: ToolResult) -> int | None:
    """How many results a search tool returned, so empty searches can be counted."""
    content = result.structured_content
    if isinstance(content, dict) and isinstance(content.get("results"), list):
        return len(content["results"])
    return None
