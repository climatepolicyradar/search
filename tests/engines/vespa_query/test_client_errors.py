"""
Tests that a failed Vespa request is raised rather than turned into no results.

"Vespa is broken" and "nothing matched your query" are different answers.
Collapsing the first into the second leaves clients unable to tell them apart,
so every failure mode of :func:`aexecute_vespa_query` must raise
:class:`VespaError`, and no caller may catch it to return an empty result.
"""

import asyncio
import json
import logging
from typing import Any

import httpx2
import pytest

from search.engines import Pagination, VespaError, dev_vespa
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
)
from search.engines.vespa_query.client import Settings
from tests.http import MockHandler


def _execute(client: httpx2.AsyncClient) -> dict[str, Any]:
    return asyncio.run(
        dev_vespa.aexecute_vespa_query(
            endpoint="http://localhost:8080/search",
            token="test-read-token",  # nosec B106
            request_body={"yql": "select * from sources documents where true"},
            request_context="test.context",
            client=client,
        )
    )


# region aexecute_vespa_query failure modes


def test_execute_raises_when_the_request_never_reaches_vespa(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """A connection-level failure is raised, with the original error chained."""
    cause = httpx2.ConnectError("connection refused")
    handler.add_error(cause)

    with pytest.raises(VespaError) as exc_info:
        _execute(http_client)

    assert "test.context" in str(exc_info.value)
    assert exc_info.value.__cause__ is cause


def test_execute_raises_on_a_timeout(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """The 5s ``API_TIMEOUT`` firing is a failure, not an empty result set."""
    handler.add_error(httpx2.ReadTimeout("timed out"))

    with pytest.raises(VespaError):
        _execute(http_client)


@pytest.mark.parametrize(
    "error",
    [httpx2.RemoteProtocolError("goaway"), httpx2.WriteError("broken pipe")],
)
def test_a_torn_down_connection_is_retried_once(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    error: Exception,
) -> None:
    """Vespa Cloud recycles connections on a timer; that is not a user-visible failure."""
    body = {"root": {"children": []}}
    handler.add_error(error)
    handler.add_response(body)

    assert _execute(http_client) == body
    assert handler.request_count == 2


def test_a_retry_that_also_fails_raises(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    handler.add_error(httpx2.RemoteProtocolError("goaway"))
    handler.add_error(httpx2.RemoteProtocolError("goaway"))

    with pytest.raises(VespaError):
        _execute(http_client)

    assert handler.request_count == 2


def test_a_refused_connection_is_not_retried(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """Re-sending this would double the load on a Vespa that is already struggling."""
    handler.add_error(httpx2.ConnectError("refused"))

    with pytest.raises(VespaError):
        _execute(http_client)

    assert handler.request_count == 1


@pytest.mark.parametrize("status_code", [400, 401, 429, 500, 502, 504])
def test_execute_raises_on_a_non_success_status_code(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    status_code: int,
) -> None:
    """Any 4xx/5xx from Vespa is raised, with the status in the message."""
    handler.add_text_response(status_code, "upstream detail")

    with pytest.raises(VespaError) as exc_info:
        _execute(http_client)

    message = str(exc_info.value)
    assert str(status_code) in message
    assert "upstream detail" in message
    # The API boundary returns this verbatim, so it has to be a status a client
    # can be given.
    assert exc_info.value.status_code == status_code


def test_execute_truncates_the_error_body_it_reports(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """A large Vespa error body is previewed, not echoed in full."""
    handler.add_text_response(500, "z" * 5000)

    with pytest.raises(VespaError) as exc_info:
        _execute(http_client)

    assert (
        str(exc_info.value).count("z") == dev_vespa.HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS
    )


@pytest.mark.parametrize("status_code", [200, 201, 204, 206])
def test_execute_raises_when_the_body_is_not_json(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    status_code: int,
) -> None:
    """
    A 2xx with an unparsable body is a failure, not an empty result set.

    ``status_code`` is None rather than the 2xx Vespa sent, because the API
    boundary returns it verbatim and would otherwise answer a request it could
    not serve with a success code. The status is kept in the message, where it
    is diagnostic rather than load-bearing.
    """
    handler.add_text_response(status_code, "not json")

    with pytest.raises(VespaError) as exc_info:
        _execute(http_client)

    assert "invalid JSON" in str(exc_info.value)
    assert str(status_code) in str(exc_info.value)
    assert exc_info.value.status_code is None


def test_execute_returns_the_decoded_body_on_success(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    body = {"root": {"children": [], "fields": {"totalCount": 0}}}
    handler.add_response(body)

    assert _execute(http_client) == body


# endregion aexecute_vespa_query failure modes

# region Callers must not swallow VespaError


def test_document_search_propagates_vespa_error(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)
    handler.add_error(httpx2.ConnectError("Vespa is down"))

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_passage_search_propagates_vespa_error(settings: Settings) -> None:

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code=500)

    transport = httpx2.MockTransport(handler)
    engine = DevVespaPassageSearchEngine(
        httpx=httpx2.AsyncClient(transport=transport),
        settings=settings,
    )

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_passage_get_with_context_propagates_vespa_error(settings) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("Vespa is down")

    engine = DevVespaPassageSearchEngine(
        httpx=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        settings=settings,
    )

    with pytest.raises(VespaError):
        asyncio.run(engine.aget_with_context("p_1_b_1", context=1))


def test_label_search_propagates_vespa_error(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    engine = DevVespaLabelSearchEngine(settings=settings, httpx=http_client)
    handler.add_error(httpx2.ConnectError("Vespa is down"))

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_document_search_surfaces_an_http_failure_end_to_end(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    """The whole path, from a 503 off the wire to the engine's caller."""
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)
    handler.add_text_response(503, "service unavailable")

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_document_search_still_returns_an_empty_list_for_no_matches(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    settings: Settings,
) -> None:
    """The counterpart: a genuinely empty result set is not an error."""
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": [], "fields": {"totalCount": 0}}})

    result = engine.search(
        query="needle",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    assert result.results == []
    assert result.total_size == 0


# endregion Callers must not swallow VespaError

# region Degraded coverage


def test_a_degraded_response_is_warned_about(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A partial answer is usable, so it warns - it does not raise."""
    body = {
        "root": {
            "coverage": {
                "coverage": 42,
                "documents": 1000,
                "degraded": {"timeout": True},
            },
            "children": [],
        }
    }
    handler.add_response(body)

    with caplog.at_level(logging.WARNING):
        assert _execute(http_client) == body

    assert "degraded" in caplog.text
    assert "test.context" in caplog.text


def test_a_full_coverage_response_is_not_warned_about(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The counterpart: a complete answer is silent."""
    body = {
        "root": {
            "coverage": {
                "coverage": 100,
                "documents": 1000,
                "degraded": {"timeout": False},
            },
            "children": [],
        }
    }
    handler.add_response(body)

    with caplog.at_level(logging.WARNING):
        _execute(http_client)

    assert "degraded" not in caplog.text


# endregion Degraded coverage

# region Timing instrumentation


def test_every_request_asks_vespa_for_timing(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    `presentation.timing` is on for every call.

    Without it a slow query cannot be attributed: FUS-479 read as a 83ms search
    when 4.5s of the budget was going on summary fetch.
    """
    handler.add_response({})

    _execute(http_client)

    assert handler.last_json()["presentation.timing"] is True


def test_a_completed_request_logs_where_the_time_went(
    caplog: pytest.LogCaptureFixture,
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """The success line splits Vespa's own timing out and records the payload size."""
    timing = {"querytime": 0.011, "summaryfetchtime": 4.457, "searchtime": 4.469}
    root = {"children": [], "fields": {"totalCount": 0}}
    body = json.dumps({"timing": timing, "root": root})
    handler.add_text_response(200, body)

    with caplog.at_level(logging.INFO):
        _execute(http_client)

    completed = [r.message for r in caplog.records if "completed" in r.message][0]
    assert "vespa_querytime_ms=11" in completed
    assert "vespa_summaryfetchtime_ms=4457" in completed
    assert "vespa_searchtime_ms=4469" in completed
    assert f"bytes={len(body)}" in completed
    assert "summary=default" in completed
    assert "elapsed_ms=" in completed


def test_a_failed_request_logs_how_long_it_waited(
    caplog: pytest.LogCaptureFixture,
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """Test that timeuts log how long they waited."""
    handler.add_error(httpx2.ReadTimeout("timed out"))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(VespaError):
            _execute(http_client)

    failed = [r.message for r in caplog.records if "before a response" in r.message][0]
    assert "elapsed_ms=" in failed


# endregion Timing instrumentation
