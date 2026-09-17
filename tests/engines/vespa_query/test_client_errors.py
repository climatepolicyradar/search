"""
Tests that a failed Vespa request is raised rather than turned into no results.

"Vespa is broken" and "nothing matched your query" are different answers.
Collapsing the first into the second leaves clients unable to tell them apart,
so every failure mode of :func:`_execute_vespa_query` must raise
:class:`VespaError`, and no caller may catch it to return an empty result.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic import AnyHttpUrl

from search.engines import Pagination, VespaError, dev_vespa
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
)
from search.engines.dev_vespa import documents_search_engine


@pytest.fixture
def settings() -> Settings:
    return Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )


def _response(
    status_code: int = 200,
    text: str = "",
    json_value: dict | None = None,
    json_error: Exception | None = None,
) -> MagicMock:
    """Build a stand-in for a ``requests.Response``."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = json_value if json_value is not None else {}
    return response


def _execute(post_fn) -> dict:
    return dev_vespa._execute_vespa_query(
        endpoint="http://localhost:8080/search",
        token="test-read-token",  # nosec B106
        request_body={"yql": "select * from sources documents where true"},
        request_context="test.context",
        post_fn=post_fn,
    )


# region _execute_vespa_query failure modes


def test_execute_raises_when_the_request_never_reaches_vespa() -> None:
    """A connection-level failure is raised, with the original error chained."""
    cause = requests.ConnectionError("connection refused")

    with pytest.raises(VespaError) as exc_info:
        _execute(MagicMock(side_effect=cause))

    assert "test.context" in str(exc_info.value)
    assert exc_info.value.__cause__ is cause


def test_execute_raises_on_a_timeout() -> None:
    """The 5s ``API_TIMEOUT`` firing is a failure, not an empty result set."""
    with pytest.raises(VespaError):
        _execute(MagicMock(side_effect=requests.Timeout("timed out")))


@pytest.mark.parametrize("status_code", [400, 401, 429, 500, 502, 504])
def test_execute_raises_on_a_non_success_status_code(status_code: int) -> None:
    """Any 4xx/5xx from Vespa is raised, with the status in the message."""
    post_fn = MagicMock(return_value=_response(status_code, text="upstream detail"))

    with pytest.raises(VespaError) as exc_info:
        _execute(post_fn)

    message = str(exc_info.value)
    assert str(status_code) in message
    assert "upstream detail" in message


def test_execute_truncates_the_error_body_it_reports() -> None:
    """A large Vespa error body is previewed, not echoed in full."""
    post_fn = MagicMock(return_value=_response(500, text="z" * 5000))

    with pytest.raises(VespaError) as exc_info:
        _execute(post_fn)

    assert (
        str(exc_info.value).count("z") == dev_vespa.HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS
    )


def test_execute_raises_when_the_body_is_not_json() -> None:
    """A 200 with an unparsable body is a failure, not an empty result set."""
    post_fn = MagicMock(
        return_value=_response(200, json_error=ValueError("not json")),
    )

    with pytest.raises(VespaError) as exc_info:
        _execute(post_fn)

    assert "invalid JSON" in str(exc_info.value)


def test_execute_returns_the_decoded_body_on_success() -> None:
    body = {"root": {"children": [], "fields": {"totalCount": 0}}}
    post_fn = MagicMock(return_value=_response(200, json_value=body))

    assert _execute(post_fn) == body


# endregion _execute_vespa_query failure modes

# region Callers must not swallow VespaError


@pytest.fixture
def failing_query():
    """Make every Vespa request fail."""
    with (
        patch.object(
            dev_vespa,
            "_execute_vespa_query",
            side_effect=VespaError("Vespa is down"),
        ) as mock_execute,
        patch.object(
            documents_search_engine,
            "_execute_vespa_query",
            side_effect=VespaError("Vespa is down"),
        ),
    ):
        yield mock_execute


def test_document_search_propagates_vespa_error(settings, failing_query) -> None:
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_document_aggregations_propagates_vespa_error(settings, failing_query) -> None:
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.aggregations(query="needle")


def test_labels_value_type_facets_propagates_vespa_error(
    settings, failing_query
) -> None:
    """Facet queries fan out across threads; the failure must still surface."""
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.labels_value_type_facets(query="needle")


def test_labels_type_facets_propagates_vespa_error(settings, failing_query) -> None:
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.labels_type_facets(query="needle")


def test_passage_search_propagates_vespa_error(settings, failing_query) -> None:
    engine = DevVespaPassageSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_label_search_propagates_vespa_error(settings, failing_query) -> None:
    engine = DevVespaLabelSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )


def test_all_label_types_propagates_vespa_error(settings, failing_query) -> None:
    engine = DevVespaLabelSearchEngine(settings=settings)

    with pytest.raises(VespaError):
        engine.all_label_types()


def _patch_http(response: MagicMock):
    """
    Intercept the real ``requests.post`` at the session layer.

    ``_execute_vespa_query``'s ``post_fn`` default is bound to ``requests.post``
    at import time, so replacing the module attribute has no effect. Patching
    ``Session.request`` leaves the real ``requests.post`` in the path.
    """
    return patch.object(requests.sessions.Session, "request", return_value=response)


def test_document_search_surfaces_an_http_failure_end_to_end(settings) -> None:
    """The whole path, from a 503 off the wire to the engine's caller."""
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with _patch_http(_response(503, text="service unavailable")):
        with pytest.raises(VespaError):
            engine.search(
                query="needle",
                pagination=Pagination(page_token=1, page_size=10),
                order_by=[],
            )


def test_document_search_still_returns_an_empty_list_for_no_matches(settings) -> None:
    """The counterpart: a genuinely empty result set is not an error."""
    engine = DevVespaDocumentSearchEngine(settings=settings)
    body = {"root": {"children": [], "fields": {"totalCount": 0}}}

    with _patch_http(_response(200, json_value=body)):
        result = engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results == []
    assert result.total_size == 0


# endregion Callers must not swallow VespaError

# region Degraded coverage


def test_a_degraded_response_is_warned_about(caplog) -> None:
    """A partial answer is usable, so it warns - it does not raise."""
    body = {
        "root": {
            "coverage": {"coverage": 42, "documents": 1000, "degraded": {"timeout": True}},
            "children": [],
        }
    }
    post_fn = MagicMock(return_value=_response(200, json_value=body))

    with caplog.at_level(logging.WARNING):
        assert _execute(post_fn) == body

    assert "degraded" in caplog.text
    assert "test.context" in caplog.text


def test_a_full_coverage_response_is_not_warned_about(caplog) -> None:
    """The counterpart: a complete answer is silent."""
    body = {
        "root": {
            "coverage": {"coverage": 100, "documents": 1000, "degraded": {"timeout": False}},
            "children": [],
        }
    }
    post_fn = MagicMock(return_value=_response(200, json_value=body))

    with caplog.at_level(logging.WARNING):
        _execute(post_fn)

    assert "degraded" not in caplog.text


# endregion Degraded coverage

# region Timing instrumentation


def test_every_request_asks_vespa_for_timing() -> None:
    """
    `presentation.timing` is on for every call.

    Without it a slow query cannot be attributed: FUS-479 read as a 83ms search
    when 4.5s of the budget was going on summary fetch.
    """
    post_fn = MagicMock(return_value=_response(200, json_value={}))

    _execute(post_fn)

    assert post_fn.call_args.kwargs["json"]["presentation.timing"] is True


def test_a_completed_request_logs_where_the_time_went(caplog) -> None:
    """The success line splits Vespa's own timing out and records the payload size."""
    response = _response(
        200,
        json_value={
            "timing": {
                "querytime": 0.011,
                "summaryfetchtime": 4.457,
                "searchtime": 4.469,
            },
            "root": {"children": [], "fields": {"totalCount": 0}},
        },
    )
    response.content = b"x" * 1234

    with caplog.at_level(logging.INFO):
        _execute(MagicMock(return_value=response))

    completed = [r.message for r in caplog.records if "completed" in r.message][0]
    assert "vespa_querytime_ms=11" in completed
    assert "vespa_summaryfetchtime_ms=4457" in completed
    assert "vespa_searchtime_ms=4469" in completed
    assert "bytes=1234" in completed
    assert "summary=default" in completed
    assert "elapsed_ms=" in completed


def test_a_failed_request_logs_how_long_it_waited(caplog) -> None:
    """Test that timeuts log how long they waited."""
    with caplog.at_level(logging.ERROR):
        with pytest.raises(VespaError):
            _execute(MagicMock(side_effect=requests.Timeout("timed out")))

    failed = [r.message for r in caplog.records if "before a response" in r.message][0]
    assert "elapsed_ms=" in failed


# endregion Timing instrumentation
