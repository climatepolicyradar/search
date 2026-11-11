import json
from http import HTTPStatus
from unittest.mock import AsyncMock, Mock, patch

import httpx2
import pytest
from pydantic import AnyHttpUrl

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
    FieldFilter,
    Filter,
    Settings,
    documents_search_engine,
    labels_search_engine,
    normalise_topic_id,
    passages_search_engine,
)
from search.engines.vespa_query.filters import _topic_ids_from_filters
from search.engines.vespa_query.sorting import _document_sort_ranking_string
from tests.http import MockHandler


@pytest.mark.parametrize(
    "s, expected",
    [
        (
            "geography::geography::USA::United States of America",
            ("geography", "geography::USA", "United States of America"),
        ),
        (
            "geography::geography::USA_west::United States of America",
            ("geography", "geography::USA_west", "United States of America"),
        ),
    ],
)
def test_parse_label_type_id_value(s, expected):
    assert DevVespaDocumentSearchEngine.parse_label_type_id_value(s) == expected


@pytest.mark.parametrize(
    ("field", "direction", "expected"),
    [
        (
            "attributes_published_date",
            "asc",
            "+missing(attributes_published_date,last)",
        ),
        (
            "attributes_published_date",
            "desc",
            "-missing(attributes_published_date,last)",
        ),
        ("title_sort", "asc", "+missing(title_sort,last)"),
        ("title_sort", "desc", "-missing(title_sort,last)"),
    ],
)
def test_document_sort_ranking_string_puts_missing_values_last(
    field: str, direction: str, expected: str
) -> None:
    assert _document_sort_ranking_string(field, direction) == expected


def _document_engine(
    http_client: httpx2.AsyncClient, **kwargs
) -> DevVespaDocumentSearchEngine:
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    return DevVespaDocumentSearchEngine(settings=settings, httpx=http_client, **kwargs)


@pytest.mark.parametrize(
    ("engine_kwargs", "expected_summary"),
    [
        ({}, "search"),
        ({"bolding": True}, "search"),
        ({"debug": True}, "debug-summary"),
        ({"debug": True, "bolding": True}, "debug-summary"),
    ],
)
def test_document_search_never_requests_the_default_summary(
    engine_kwargs: dict, expected_summary: str, http_client: httpx2.AsyncClient
) -> None:
    """Every search hit summary must be one of the summaries with trimmed fields."""
    engine = _document_engine(http_client, **engine_kwargs)

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["presentation.summary"] == expected_summary


def test_document_search_hits_carry_no_passages(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    Search hits never carry passages, whatever Vespa returns.

    `matched-elements-only` still returns every passage that matched, which for
    numeric queries is thousands per document (~10MB a page). `/search/passages`
    is the route for passages; document hits stay lean (FUS-479).
    """
    engine = _document_engine(http_client, bolding=True)

    fake_response = {
        "root": {
            "children": [
                {
                    "id": "id:documents:documents::doc-0",
                    "fields": {
                        "document_source": (
                            '{"id": "doc-0", "labels": [], "documents": []}'
                        ),
                        "passages_text": ["<hi>needle</hi> in a haystack"],
                    },
                }
            ]
        }
    }

    with patch.object(
        documents_search_engine, "aexecute_vespa_query", return_value=fake_response
    ):
        result = engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results[0].passages == []





def test_passage_search_engine_reads_pages_from_top_level_passages_schema(
    passage_engine: DevVespaPassageSearchEngine,
    handler: MockHandler,
) -> None:
    """The top-level passages schema's pages struct field lands on Passage.pages."""
    handler.add_response({
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "block-0",
                        "idx": 0,
                        "content": "some text",
                        "language": "en",
                        "content_type": "Text",
                        "type_confidence": 1.0,
                        "pages": [
                            {"number": 5, "bounding_boxes": []},
                            {"number": 6, "bounding_boxes": []},
                        ],
                        "document_id": "doc-0",
                    }
                }
            ]
        }
    })

    result = passage_engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    assert result.results[0].pages == [5, 6]
    assert result.results[0].type == "Text"
    assert result.results[0].text == "some text"


def test_passage_search_engine_applies_order_by_to_request_body(
    passage_engine: DevVespaPassageSearchEngine,
    handler: MockHandler,
) -> None:
    """A non-empty ``order_by`` produces ``ranking.sorting`` on the Vespa request."""
    handler.add_response({"root": {"children": []}})

    passage_engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="idx", direction="desc")],
    )

    request_body = handler.last_json()
    assert request_body["ranking.profile"] == "unranked"
    assert request_body["ranking.sorting"] == "-missing(idx,last)"
    assert request_body["sorting.degrading"] is False


def test_passage_search_engine_order_by_wins_over_debug_mode_ranking_profile(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    An explicit order_by sort overrides debug mode's rank-profile choice profile.

    Matches ``DevVespaDocumentSearchEngine.search``, where sort overrides are
    always applied after any default/debug ``ranking.profile`` is set.
    """
    engine = DevVespaPassageSearchEngine(
        settings=_KSTEM_SETTINGS,
        httpx=http_client,
        debug=True,
    )

    handler.add_response({"root": {"children": []}})

    engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="idx", direction="asc")],
    )

    request_body = handler.last_json()
    assert request_body["ranking.profile"] == "unranked"
    assert request_body["ranking.sorting"] == "+missing(idx,last)"


def test_passage_search_engine_reads_page_bounding_boxes_from_top_level_passages_schema(
    passage_engine: DevVespaPassageSearchEngine,
    handler: MockHandler,
) -> None:
    """The top-level passages schema's pages struct field lands on Passage.pages_with_bounding_boxes."""
    handler.add_response({
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "block-0",
                        "idx": 0,
                        "content": "some text",
                        "language": "en",
                        "content_type": "Text",
                        "type_confidence": 1.0,
                        "pages": [
                            {
                                "number": 5,
                                "bounding_boxes": [
                                    {"coordinates": [{"x": 0.1, "y": 0.2}]}
                                ],
                            },
                            {
                                "number": 6,
                                "bounding_boxes": [],
                            },
                        ],
                        "document_id": "doc-0",
                    }
                }
            ]
        }
    })

    result = passage_engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    passage = result.results[0]
    assert len(passage.pages_with_bounding_boxes) == 2
    assert passage.pages_with_bounding_boxes[0].number == 5
    assert (
        passage.pages_with_bounding_boxes[0].bounding_boxes[0].coordinates[0].x == 0.1
    )
    assert passage.pages_with_bounding_boxes[1].number == 6
    assert passage.pages_with_bounding_boxes[1].bounding_boxes == []


def test_passage_search_engine_reads_labels_from_top_level_passages_schema(
    passage_engine: DevVespaPassageSearchEngine,
    handler: MockHandler,
) -> None:
    """The top-level passages schema's labels field lands on Passage.labels."""
    handler.add_response({
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "block-0",
                        "idx": 0,
                        "content": "some text",
                        "language": "en",
                        "content_type": "Text",
                        "type_confidence": 1.0,
                        "labels": [
                            {
                                "id": "concept::finance flow",
                                "type": "concept",
                                "value": "finance flow",
                                "classifier_id": "classifier-1",
                                "end_index": 12.0,
                                "labelled_text": "finance flow",
                                "labellers": ["classifier-1"],
                                "prediction_probability": 0.9,
                                "start_index": 0.0,
                                "timestamps": ["2024-01-01T00:00:00"],
                            },
                            {
                                "id": "concept::drought",
                                "type": "concept",
                                "value": "drought",
                                "classifier_id": "classifier-2",
                                "end_index": 20.0,
                                "labelled_text": "drought",
                                "labellers": ["classifier-2"],
                                "prediction_probability": 0.8,
                                "start_index": 14.0,
                                "timestamps": ["2024-01-02T00:00:00"],
                            },
                        ],
                        "document_id": "doc-0",
                    }
                }
            ]
        }
    })

    result = passage_engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    passage = result.results[0]
    assert len(passage.labels) == 2
    assert passage.labels[0].value.id == "concept::finance flow"
    assert passage.labels[0].value.type == "concept"
    assert passage.labels[0].value.value == "finance flow"
    assert passage.labels[0].classifier_id == "classifier-1"
    assert passage.labels[0].prediction_probability == 0.9
    assert passage.labels[1].value.value == "drought"
    assert passage.labels[1].classifier_id == "classifier-2"


def _topic_filter(*topics: str, op: str = "and") -> Filter:
    """A filter in the nested shape `_build_topic_filter` produces."""
    return Filter(
        op=op,  # pyright: ignore[reportArgumentType]
        filters=[
            Filter(
                op="or",
                filters=[
                    FieldFilter(
                        field="labels.value.id",
                        op="contains",
                        value=normalise_topic_id(topic),
                    )
                ],
            )
            for topic in topics
        ],
    )


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (None, []),
        (Filter(op="and", filters=[]), []),
        (
            Filter(
                op="and",
                filters=[
                    FieldFilter(
                        field="labels.value.id", op="contains", value="concept::Q567"
                    )
                ],
            ),
            ["concept::Q567"],
        ),
        # Nested groups, as `_build_topic_filter` produces for multiple topics.
        (
            Filter(
                op="and",
                filters=[
                    Filter(
                        op="or",
                        filters=[
                            FieldFilter(
                                field="labels.value.id",
                                op="contains",
                                value="concept::Q567",
                            )
                        ],
                    ),
                    Filter(
                        op="or",
                        filters=[
                            FieldFilter(
                                field="labels.value.id",
                                op="contains",
                                value="concept::Q1651",
                            )
                        ],
                    ),
                ],
            ),
            ["concept::Q567", "concept::Q1651"],
        ),
        # Excluding a topic must not boost it.
        (
            Filter(
                op="and",
                filters=[
                    FieldFilter(
                        field="labels.value.id",
                        op="not_contains",
                        value="concept::Q567",
                    )
                ],
            ),
            [],
        ),
        # Non-concept labels filtered on the same field are not topics.
        (
            Filter(
                op="and",
                filters=[
                    FieldFilter(
                        field="labels.value.id", op="contains", value="country::AUS"
                    ),
                    FieldFilter(
                        field="labels.value.id", op="contains", value="concept::Q567"
                    ),
                ],
            ),
            ["concept::Q567"],
        ),
        # Other fields are ignored.
        (
            Filter(
                op="and",
                filters=[
                    FieldFilter(
                        field="labels.value.value", op="contains", value="concept::Q567"
                    )
                ],
            ),
            [],
        ),
        # Repeats collapse.
        (
            Filter(
                op="or",
                filters=[
                    FieldFilter(
                        field="labels.value.id", op="contains", value="concept::Q567"
                    ),
                    FieldFilter(
                        field="labels.value.id", op="contains", value="concept::Q567"
                    ),
                ],
            ),
            ["concept::Q567"],
        ),
    ],
)
def test_topic_ids_from_filters(filters: Filter | None, expected: list[str]) -> None:
    assert _topic_ids_from_filters(filters) == expected


def test_document_search_engine_sends_filtered_topics_as_a_query_tensor(
    http_client: httpx2.AsyncClient,
) -> None:
    """Topics being filtered for become the topic ranking tensor."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters=_topic_filter("Q567", "Q1651"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == _DEFAULT_DOCUMENT_RANK_PROFILE
    assert request_body["input.query(topic_q)"] == {
        "concept::Q567": 1.0,
        "concept::Q1651": 1.0,
    }
    assert request_body["input.query(topic_weight)"] == 1.0


def test_document_search_engine_omits_topic_inputs_without_topics_filter(
    http_client: httpx2.AsyncClient,
) -> None:
    """No topic filter means no topic inputs, leaving ranking exactly as it was."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "input.query(topic_q)" not in request_body
    assert "input.query(topic_weight)" not in request_body


def test_document_search_engine_forwards_topic_weight(
    http_client: httpx2.AsyncClient,
) -> None:
    """`topic_weight=0.0` is the off switch for topic ranking."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(
        settings=settings, httpx=http_client, topic_weight=0.0
    )

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters=_topic_filter("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["input.query(topic_weight)"] == 0.0
    # Surfaced for relevance-test logging rather than baked into the engine name.
    assert engine.parameters["topic_weight"] == 0.0
    assert engine.name == "DevVespaDocumentSearchEngine"


def test_document_search_engine_omits_topic_inputs_under_a_sort_override(
    http_client: httpx2.AsyncClient,
) -> None:
    """Topics ranking should be disabled when sorting by a field is specified."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="title", direction="asc")],
            filters=_topic_filter("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert "input.query(topic_q)" not in request_body
    assert "input.query(topic_weight)" not in request_body


def test_passage_search_engine_sends_ranking_profile_without_debug(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    The rank profile is sent on every request, not just debug ones.

    Without this the live API falls through to Vespa's implicit `default`
    profile silently.
    """
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    request_body = handler.last_json()
    assert request_body["ranking.profile"] == passages_search_engine.DEFAULT_PASSAGE_RANK_PROFILE


@pytest.mark.parametrize(
    ("debug", "expected_summary"),
    [(False, "search"), (True, "debug-summary")],
)
def test_passage_search_engine_requests_the_search_summary_unless_debugging(
    debug: bool,
    expected_summary: str,
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """Live requests use the in-memory `search` summary; `debug=True` uses `debug-summary`."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client, debug=debug)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    request_body = handler.last_json()
    assert request_body["presentation.summary"] == expected_summary


def test_passage_search_engine_sends_filtered_topics_as_a_query_tensor(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """Topics being filtered for become the topic ranking tensor."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
        filters=_topic_filter("Q567", "Q1651"),
    )

    request_body = handler.last_json()
    assert request_body["input.query(topic_q)"] == {
        "concept::Q567": 1.0,
        "concept::Q1651": 1.0,
    }
    assert request_body["input.query(topic_weight)"] == 1.0


def test_passage_search_engine_sends_topic_inputs_without_a_text_query(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    Topic-only searches are the case topic ranking matters most for.

    Passage relevance tests routinely pass `search_terms=""`, where the topic
    score is the only signal - so the inputs must not be gated on `userQuery()`.
    """
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query="",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
        filters=_topic_filter("Q567"),
    )

    request_body = handler.last_json()
    assert "userQuery()" not in request_body["yql"]
    assert request_body["input.query(topic_q)"] == {"concept::Q567": 1.0}


def test_passage_search_engine_forwards_topic_weight(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """We can use `topic_weight=0.0` to switch off topic ranking."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client, topic_weight=0.0)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
        filters=_topic_filter("Q567"),
    )

    request_body = handler.last_json()
    assert request_body["input.query(topic_weight)"] == 0.0
    assert engine.parameters == {
        "ranking_profile": passages_search_engine.DEFAULT_PASSAGE_RANK_PROFILE,
        "topic_weight": 0.0,
        "exact_weight": 0.1,
    }
    assert engine.name == "DevVespaPassageSearchEngine"


def test_passage_search_engine_omits_topic_inputs_under_a_sort_override(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """Topic ranking should be disabled when sorting by a field is specified."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query="some",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="idx", direction="asc")],
        filters=_topic_filter("Q567"),
    )

    request_body = handler.last_json()
    assert request_body["ranking.profile"] == "unranked"
    assert "input.query(topic_q)" not in request_body
    assert "input.query(topic_weight)" not in request_body


def test_document_get_renders_labels_and_concepts(
    http_client: httpx2.AsyncClient,
) -> None:
    """`get` renders a document like a search hit with labels with concepts."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)

    document_source = json.dumps(
        {
            "id": "doc-0",
            "title": "Climate Policy",
            "labels": [
                {
                    "type": "has_geography",
                    "value": {
                        "id": "geography::USA",
                        "type": "geography",
                        "value": "United States of America",
                    },
                }
            ],
            "documents": [],
        }
    )
    # Concepts are fed as a partial update, so they are only ever in `fields`.
    response = Mock(status_code=HTTPStatus.OK)
    response.json.return_value = {
        "fields": {
            "document_source": document_source,
            "concepts": [
                {
                    "id": "concept::Q1343",
                    "type": "concept",
                    "value": "climate finance",
                    "count": 42,
                    "passages_id": "passages-0",
                    "document_id": "doc-1",
                }
            ],
        }
    }

    with patch.object(httpx2.AsyncClient, "get", new=AsyncMock(return_value=response)):
        document = engine.get("doc-0")

    assert document is not None
    source_label, concept_label = document.labels
    assert source_label.type == "has_geography"
    assert source_label.value.id == "geography::USA"
    assert concept_label.type == "concept"
    assert concept_label.value.id == "concept::Q1343"
    assert concept_label.value.value == "climate finance"
    assert concept_label.count == 42
    assert concept_label.passages_id is None
    assert concept_label.document_id == "doc-1"
    assert source_label.document_id is None


def test_passage_search_engine_quoted_query_builds_exact_phrase(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """A fully-quoted passage query becomes an in-order phrase on the unstemmed field."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query='"net zero"',
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    request_body = handler.last_json()
    yql = request_body["yql"]
    assert "content_not_stemmed contains" in yql
    assert "{grammar.composite:'phrase'}text(@exact_phrase_0)" in yql
    assert "userQuery()" not in yql
    assert request_body["exact_phrase_0"] == "net zero"
    assert "query" not in request_body


def test_passage_search_engine_mixes_free_term_and_phrase(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """'brazil "net zero"' -> free term via userQuery() AND an exact phrase."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, httpx=http_client)
    handler.add_response({"root": {"children": []}})

    engine.search(
        query='brazil "net zero"',
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )

    request_body = handler.last_json()
    assert '{grammar.profile: "passage_analysis_kstem"}userInput(@query)' in request_body["yql"]
    assert "content_not_stemmed contains" in request_body["yql"]
    assert request_body["query"] == "brazil"
    assert request_body["exact_phrase_0"] == "net zero"


def test_document_search_engine_quoted_query_builds_exact_phrase(
    http_client: httpx2.AsyncClient,
) -> None:
    """A fully-quoted document query phrase-matches title, description AND passages_text."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)

    with patch.object(
        documents_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query='"just transition"',
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    yql = request_body["yql"]
    assert "title_not_stemmed contains" in yql
    assert "description_not_stemmed contains" in yql
    assert "passages_text_not_stemmed contains" in yql
    assert "userQuery()" not in yql
    assert request_body["exact_phrase_0"] == "just transition"
    assert "query" not in request_body


def _document_search_yql(engine: DevVespaDocumentSearchEngine) -> str:
    """Run a text search against a mocked Vespa and return the YQL it sent."""
    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query="electric arc furnace",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    return mock_execute.call_args.kwargs["request_body"]["yql"]


def test_document_search_engine_sends_default_target_hits(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    Retrieval depth is stated in the YQL rather than left to Vespa's default.

    `totalTargetHits` binds to `userInput()` only - on `userQuery()` it parses
    and is then silently ignored - so the clause must not fall back to
    `userQuery()`. It is cluster-wide, unlike the per-node `targetHits`.
    """
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=http_client)

    yql = _document_search_yql(engine)

    assert '{totalTargetHits:2000, grammar.profile: "passage_analysis_kstem"}userInput(@query)' in yql
    assert "userQuery()" not in yql
    assert engine.parameters["total_target_hits"] == 2000


def test_document_search_engine_forwards_target_hits(
    http_client: httpx2.AsyncClient,
) -> None:
    """`total_target_hits` overrides how many candidates weakAnd keeps."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(
        settings=settings, httpx=http_client, total_target_hits=200
    )

    yql = _document_search_yql(engine)

    assert '{totalTargetHits:200, grammar.profile: "passage_analysis_kstem"}userInput(@query)' in yql
    # The geography and identifier arms are untouched by the change.
    assert '{defaultIndex: "geographies"}userInput(@geo_query)' in yql
    assert '{defaultIndex: "identifiers"}userInput(@query)' in yql
    assert engine.parameters["total_target_hits"] == 200


# region Minimum Should Match


def _document_search_request_body(
    engine: DevVespaDocumentSearchEngine,
    order_by: list[OrderBy] = [],  # noqa: B006 - read-only, never mutated
    query: str = "parametric insurance act",
) -> dict:
    """Run a text search against a mocked Vespa and return the body it sent."""
    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.search(
            query=query,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=order_by,
        )

    return mock_execute.call_args.kwargs["request_body"]


def test_msm_defaults_to_off_and_changes_nothing(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    MSM off must be byte-identical to the behaviour that predates it.

    The default rank profile carries no `rank-score-drop-limit`, so sending
    `query(msm)` to it would be a silent no-op rather than a filter.
    """
    engine = _document_engine(http_client)

    body = _document_search_request_body(engine)

    assert engine.msm == 0.0
    assert body["ranking.profile"] == _DEFAULT_DOCUMENT_RANK_PROFILE
    assert "input.query(msm)" not in body


def test_msm_forwards_the_value_on_the_default_profile(
    http_client: httpx2.AsyncClient,
) -> None:
    """`bm25-title-geo` declares query(msm), so no profile switch is needed."""
    engine = _document_engine(http_client, msm=0.6)

    body = _document_search_request_body(engine)

    assert body["ranking.profile"] == _DEFAULT_DOCUMENT_RANK_PROFILE
    assert body["input.query(msm)"] == 0.6
    assert engine.parameters["msm"] == 0.6


def test_msm_survives_a_sort(http_client: httpx2.AsyncClient) -> None:
    """
    A sorted listing must not return documents a relevance search would drop.

    `unranked` declares query(msm) and carries the same guard, so a sort filters
    without needing a profile of its own.
    """
    engine = _document_engine(http_client, msm=0.6)

    body = _document_search_request_body(
        engine, order_by=[OrderBy(field="attributes.published_date", direction="desc")]
    )

    assert body["ranking.profile"] == "unranked"
    assert body["input.query(msm)"] == 0.6
    assert body["ranking.sorting"]


def test_msm_reaches_aggregations_and_facets(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    Facet counts and results have to describe the same document set.

    These run as separate Vespa queries; a facet counted over a wider set than
    the results is the inconsistency FUS-475 was about.
    """
    engine = _document_engine(http_client, msm=0.6)

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.aggregations(query="parametric insurance act")
        engine.labels_type_facets(query="parametric insurance act")

    for call in mock_execute.call_args_list:
        body = call.kwargs["request_body"]
        assert body["input.query(msm)"] == 0.6
        assert body["ranking.profile"] == _DEFAULT_DOCUMENT_RANK_PROFILE


def test_msm_is_off_for_a_phrase_only_query(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    A quoted-only query has no free text, so `coverage()` is 0 for every document.

    Sending `query(msm)` would drop the whole corpus - every quoted search on the
    site returned nothing once the frontend started sending msm.
    """
    engine = _document_engine(http_client, msm=0.6)

    body = _document_search_request_body(engine, query='"net zero"')

    assert "input.query(msm)" not in body

    with patch.object(
        documents_search_engine,
        "aexecute_vespa_query",
        return_value={"root": {"children": []}},
    ) as mock_execute:
        engine.aggregations(query='"net zero"')
        engine.labels_type_facets(query='"net zero"')

    for call in mock_execute.call_args_list:
        assert "input.query(msm)" not in call.kwargs["request_body"]


def test_msm_still_applies_to_free_text_beside_a_phrase(
    http_client: httpx2.AsyncClient,
) -> None:
    """Free text next to a phrase still has terms for `coverage()` to measure."""
    engine = _document_engine(http_client, msm=0.6)

    body = _document_search_request_body(engine, query='UK "net zero"')

    assert body["input.query(msm)"] == 0.6


@pytest.mark.parametrize("msm", [-0.1, 1.1, 2.0])
def test_msm_out_of_range_raises(
    msm: float, http_client: httpx2.AsyncClient
) -> None:
    """An out-of-range msm is a caller error, not something to clamp silently."""
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        _document_engine(http_client, msm=msm)


def test_an_explicit_rank_profile_is_respected(
    http_client: httpx2.AsyncClient,
) -> None:
    """Relevance sweeps pin a profile; nothing may override that."""
    engine = _document_engine(http_client, ranking_profile="bm25")

    assert engine.ranking_profile == "bm25"


# endregion Minimum Should Match


def _label_engine(
    http_client: httpx2.AsyncClient, **kwargs
) -> DevVespaLabelSearchEngine:
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    return DevVespaLabelSearchEngine(settings=settings, httpx=http_client, **kwargs)


@pytest.mark.parametrize(
    ("page_token", "page_size", "expected_offset"),
    [
        (1, 10, 0),
        (2, 10, 10),
        (10, 10, 90),
        (1, 1000, 0),
    ],
)
def test_label_search_engine_computes_offset_from_page_token(
    page_token: int, page_size: int, expected_offset: int, http_client: httpx2.AsyncClient
) -> None:
    """`offset` is derived from `page_token`, not passed straight through."""
    engine = _label_engine(http_client)

    with patch.object(
        labels_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=page_token, page_size=page_size),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["offset"] == expected_offset
    assert request_body["hits"] == page_size


@pytest.mark.xfail(
    reason="order_by is a documented no-op for labels "
    "(search/engines/dev_vespa/labels_search_engine.py's "
    "DevVespaLabelSearchEngine.search()). Canary for when that changes - see "
    "test_vespa_labels_e2e.py's order_by tests for the full rationale.",
    strict=True,
    raises=AssertionError,
)
def test_label_search_engine_applies_order_by_to_request_body(
    http_client: httpx2.AsyncClient,
) -> None:
    """order_by should override ranking/sorting the way it does for passages."""
    engine = _label_engine(http_client)

    with patch.object(
        labels_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="value", direction="desc")],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "ranking.sorting" in request_body


def test_label_search_engine_filters_by_label_type(
    http_client: httpx2.AsyncClient,
) -> None:
    """A `label_type` argument adds a `type contains` clause to the YQL."""
    engine = _label_engine(http_client)

    with patch.object(
        labels_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            label_type="country",
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert 'type contains "country"' in request_body["yql"]


def test_label_search_engine_omits_type_clause_without_label_type(
    http_client: httpx2.AsyncClient,
) -> None:
    """No `label_type` means no `type contains` clause in the YQL."""
    engine = _label_engine(http_client)

    with patch.object(
        labels_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "type contains" not in request_body["yql"]


def test_label_search_engine_applies_filters_to_yql(
    http_client: httpx2.AsyncClient,
) -> None:
    """`filters` are folded into the YQL `where` clause."""
    engine = _label_engine(http_client)
    filters = Filter(
        op="and",
        filters=[FieldFilter(field="type", op="not_contains", value="keyword")],
    )

    with patch.object(
        labels_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters=filters,
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert '!(type contains "keyword")' in request_body["yql"]


def test_label_search_engine_strips_quotes_from_query(
    http_client: httpx2.AsyncClient,
) -> None:
    """Query text is quote-stripped before being sent to Vespa (matches doc/passage engines)."""
    engine = _label_engine(http_client)

    with patch.object(
        labels_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query='"Romania"',
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["query"] == "Romania"


def test_label_search_engine_parses_valid_flat_fields(
    http_client: httpx2.AsyncClient,
) -> None:
    """A hit with valid `id`/`type`/`value` fields becomes a result label."""
    engine = _label_engine(http_client)
    fake_response = {
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "geography::Romania",
                        "type": "geography",
                        "value": "Romania",
                    }
                },
            ]
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert len(result.results) == 1
    assert result.results[0].id == "geography::Romania"
    assert result.results[0].labels == []


def test_label_search_engine_parses_label_relationships(
    http_client: httpx2.AsyncClient,
) -> None:
    """The `labels` struct array becomes nested `LabelRelationship` entries."""
    engine = _label_engine(http_client)
    fake_response = {
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "country::Canada",
                        "type": "country",
                        "value": "Canada",
                        "labels": [
                            {
                                "id": "region::North America",
                                "type": "region",
                                "value": "North America",
                                "timestamp": 1700000000,
                                "relationship": "subconcept_of",
                            }
                        ],
                    }
                },
            ]
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert len(result.results) == 1
    [relationship] = result.results[0].labels
    assert relationship.type == "subconcept_of"
    assert relationship.value.id == "region::North America"
    assert relationship.timestamp is not None


def test_label_search_engine_skips_hits_with_missing_fields(
    http_client: httpx2.AsyncClient,
) -> None:
    """A hit missing a required flat field is dropped, not raised."""
    engine = _label_engine(http_client)
    fake_response = {
        "root": {
            "children": [
                {"fields": {"id": "geography::Romania", "type": "geography"}},
            ]
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results == []


def test_label_search_engine_skips_hits_with_empty_fields(
    http_client: httpx2.AsyncClient,
) -> None:
    """A hit with no fields at all is dropped, not raised."""
    engine = _label_engine(http_client)
    fake_response = {
        "root": {
            "children": [
                {"fields": {}},
            ]
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results == []


def test_label_search_engine_populates_debug_info_when_debugging(
    http_client: httpx2.AsyncClient,
) -> None:
    """`debug=True` records per-hit relevance/summary info on `last_debug_info`."""
    engine = _label_engine(http_client, debug=True)
    fake_response = {
        "root": {
            "children": [
                {
                    "relevance": 0.5,
                    "fields": {
                        "id": "geography::Romania",
                        "type": "geography",
                        "value": "Romania",
                    },
                },
            ]
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert len(engine.last_debug_info) == 1
    assert engine.last_debug_info[0]["relevance"] == 0.5
    assert engine.last_debug_info[0]["value"] == "Romania"


def test_label_search_engine_omits_debug_info_by_default(
    http_client: httpx2.AsyncClient,
) -> None:
    """Without `debug=True`, no per-hit debug info is collected."""
    engine = _label_engine(http_client)
    fake_response = {
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "geography::Romania",
                        "type": "geography",
                        "value": "Romania",
                    }
                },
            ]
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert engine.last_debug_info == []


def test_label_search_engine_reads_total_size_from_response(
    http_client: httpx2.AsyncClient,
) -> None:
    """`total_size` is read from the Vespa response's `totalCount` field."""
    engine = _label_engine(http_client)
    fake_response = {
        "root": {
            "fields": {"totalCount": 42},
            "children": [],
        }
    }

    with patch.object(labels_search_engine, "aexecute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.total_size == 42



_KSTEM_SETTINGS = Settings(
    vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
    vespa_read_token="test-read-token",  # nosec B106
)


def _passage_request_body(
    engine: DevVespaPassageSearchEngine,
    order_by: list[OrderBy],
    handler: MockHandler,
) -> dict:
    handler.add_response({"root": {"children": []}})
    engine.search(
        query="informal settlements",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=order_by,
    )
    return handler.last_json()


def test_passage_free_text_names_the_linguistics_profile(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """A fieldset query stems with Vespa's fallback stemmer unless the profile is named."""
    engine = DevVespaPassageSearchEngine(settings=_KSTEM_SETTINGS, httpx=http_client)
    body = _passage_request_body(engine, [], handler)
    assert '{grammar.profile: "passage_analysis_kstem"}userInput(@query)' in body["yql"]
    assert "userQuery()" not in body["yql"]


def test_passage_exact_boost_is_on_by_default(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """Unquoted terms also score against the unstemmed copy, for ranking only."""
    engine = DevVespaPassageSearchEngine(settings=_KSTEM_SETTINGS, httpx=http_client)
    body = _passage_request_body(engine, [], handler)
    assert " and rank(" in body["yql"]
    assert '({defaultIndex: "exact", grammar: "any"}userInput(@query)))' in body["yql"]
    assert body["input.query(exact_weight)"] == 0.1


def test_passage_exact_boost_can_be_switched_off(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    engine = DevVespaPassageSearchEngine(
        settings=_KSTEM_SETTINGS, httpx=http_client, exact_weight=None
    )
    body = _passage_request_body(engine, [], handler)
    assert "rank(" not in body["yql"]
    assert "input.query(exact_weight)" not in body
    assert ' and ({grammar.profile: "passage_analysis_kstem"}userInput(@query))' in body["yql"]


def test_passage_exact_weight_is_not_sent_under_a_sort_override(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """The sort profiles don't declare the input, so it is only sent when ranking."""
    engine = DevVespaPassageSearchEngine(settings=_KSTEM_SETTINGS, httpx=http_client)
    body = _passage_request_body(
        engine,
        [OrderBy(field="idx", direction="asc")],
        handler,
    )
    assert "input.query(exact_weight)" not in body


def test_negative_exact_weight_raises(http_client: httpx2.AsyncClient) -> None:
    with pytest.raises(ValueError, match="exact_weight"):
        DevVespaPassageSearchEngine(settings=_KSTEM_SETTINGS, httpx=http_client, exact_weight=-1.0)
    with pytest.raises(ValueError, match="exact_weight"):
        DevVespaDocumentSearchEngine(
            settings=_KSTEM_SETTINGS, httpx=http_client, exact_weight=-1.0
        )


def _document_request_body(engine: DevVespaDocumentSearchEngine) -> dict:
    with patch.object(
        documents_search_engine, "aexecute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="informal settlements",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )
    return mock_execute.call_args.kwargs["request_body"]


def test_document_exact_boost_is_off_by_default(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    Documents leave the unstemmed copies out of unquoted queries.

    `exact_phrase_score` sums bm25 over every passage, so any boost let documents
    that mention the query words often outrank the one whose title it is. `None`
    (not 0.0) also leaves quoted phrases on the schema's default weight.
    """
    engine = DevVespaDocumentSearchEngine(settings=_KSTEM_SETTINGS, httpx=http_client)
    body = _document_request_body(engine)
    assert "rank(" not in body["yql"]
    assert "input.query(exact_weight)" not in body
    assert '{totalTargetHits:2000, grammar.profile: "passage_analysis_kstem"}userInput(@query)' in body["yql"]
    assert engine.parameters["exact_weight"] is None


def test_document_exact_boost_can_be_switched_on(
    http_client: httpx2.AsyncClient,
) -> None:
    body = _document_request_body(
        DevVespaDocumentSearchEngine(
            settings=_KSTEM_SETTINGS, httpx=http_client, exact_weight=0.5
        )
    )
    assert body["yql"].count(" and rank(((") == 1
    assert '({defaultIndex: "exact", grammar: "any"}userInput(@query)))' in body["yql"]
    assert body["input.query(exact_weight)"] == 0.5


def test_document_search_leaves_an_absent_description_empty(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    A document with no description comes back as `None`, not `"MISSING"`.

    `MISSING_PLACEHOLDER` is a debugging aid for values that should always
    exist. `description` is genuinely optional (`str | None` on BaseDocument),
    so an absent one must stay empty and let the card render nothing, rather
    than printing the placeholder to users (FUS-649).
    """
    engine = _document_engine(http_client, bolding=True)

    fake_response = {
        "root": {
            "children": [
                {
                    "id": "id:documents:documents::doc-0",
                    "fields": {
                        "document_source": (
                            '{"id": "doc-0", "labels": [], "documents": []}'
                        ),
                        "title": "Third National Communication",
                        # no `description` key at all
                    },
                }
            ]
        }
    }

    with patch.object(
        documents_search_engine, "aexecute_vespa_query", return_value=fake_response
    ):
        result = engine.search(
            query="communication",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results[0].description is None


def test_document_search_absent_description_survives_exact_bolding(
    http_client: httpx2.AsyncClient,
) -> None:
    """
    A document with no description survives a quoted search.

    Vespa wraps matched words in `<hi>` tags so the UI can embolden them. A
    quoted query matches two copies of each field: `description`, stemmed,
    bolds the free text; `description_not_stemmed` bolds the literal phrase.
    `_merge_exact_bolding` combines the two.

    `merge_bolded` requires both copies to be the same text once the tags
    are stripped, or the tag positions refer to different strings. With no
    description there is no base text to line the phrase copy up against,
    so it raises `ValueError: Bolded copies of a field do not share the same
    text`. The absence has to be checked before the merge, not after.

    On `main` the `MISSING_PLACEHOLDER` default mismatched the phrase copy
    the same way, so the request failed rather than rendering "MISSING".
    Only quoted queries reach this path.
    """
    engine = _document_engine(http_client, bolding=True)

    fake_response = {
        "root": {
            "children": [
                {
                    "id": "id:documents:documents::doc-0",
                    "fields": {
                        "document_source": (
                            '{"id": "doc-0", "labels": [], "documents": []}'
                        ),
                        # no `description`, but the phrase copy came back
                        "description_not_stemmed": "<hi>carbon tax</hi>",
                    },
                }
            ]
        }
    }

    with patch.object(
        documents_search_engine, "aexecute_vespa_query", return_value=fake_response
    ):
        result = engine.search(
            # Quoted: only a query with phrases asks for `search-exact`.
            query='"carbon tax"',
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results[0].description is None



_QUERY_YQL = (
    'rank(({grammar.profile: "passage_analysis_kstem"}userInput(@query)),'
    ' ({defaultIndex: "exact", grammar: "any"}userInput(@query)))'
)
_TOPIC_YQL = 'labels contains sameElement(id contains "concept::Q1")'


@pytest.fixture
def passage_engine(http_client: httpx2.AsyncClient) -> DevVespaPassageSearchEngine:
    return DevVespaPassageSearchEngine(
        settings=Settings(
            vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
            vespa_read_token="test-read-token",  # nosec B106
        ),
        httpx=http_client,
    )


def test_passage_search_and_query_and_filters(
    passage_engine: DevVespaPassageSearchEngine,
) -> None:
    filters = Filter(
        op="or",
        filters=[
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="concept::Q1",
            ),
        ],
    )

    where = passage_engine._where_yql("flood", [], filters)

    assert where == f"true and {_TOPIC_YQL} and {_QUERY_YQL}"


def test_passage_search_within_ors_query_and_filters(
    passage_engine: DevVespaPassageSearchEngine,
) -> None:
    filters = Filter(
        op="or",
        filters=[
            FieldFilter(
                field="labels.value.id",
                value="concept::Q1",
                op="contains",
            ),
        ],
    )

    where = passage_engine._scoped_where_yql("flood", [], filters)

    assert where == (
        "true"
        " and (document_id in (@document_ids) or principal_id in (@document_ids))"
        f' and ({_QUERY_YQL} or labeled({_TOPIC_YQL}, "filters", 1.0))'
    )


@pytest.mark.parametrize(
    ("msm", "free_text", "expected"),
    [
        (0.7, "flood", {"input.query(msm)": 0.7}),
        (0.0, "flood", {}),
        (0.7, "", {}),
    ],
)
def test_passage_msm_is_only_sent_with_free_text(
    msm: float,
    free_text: str,
    expected: dict[str, float],
) -> None:
    assert passages_search_engine._msm_request_fields(msm, free_text) == expected


def _export_hit(
    id: str,
    collection_id: str | None = None,
) -> dict[str, object]:
    fields: dict[str, object] = {"id": id, "title_attribute": "t"}
    if collection_id is not None:
        fields["collection_id"] = collection_id
    return {"fields": fields}


async def test_export_reads_the_csv_summary_class(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    The export must not answer from `search`, which is backed by disk.

    Every field a CSV column reads is an attribute, and `csv` is the summary
    class that says so - asking for `search` would load the whole document row,
    passages included, for every row of the file.
    """
    engine = _document_engine(http_client)
    handler.add_response({"root": {"children": []}})

    await engine.export(
        query="needle",
        limit=10,
        order_by=[],
    )

    assert handler.last_json()["presentation.summary"] == "csv"


async def test_export_matches_the_search_where_clause(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """A download must cover the same documents as the search it was run from."""
    engine = _document_engine(http_client)
    filters = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.id", op="contains", value="geography::USA"),
        ],
    )
    handler.add_response({"root": {"children": []}})
    handler.add_response({"root": {"children": []}})

    await engine.export(
        query='toxic "waste site"',
        limit=10,
        order_by=[],
        filters=filters,
    )
    await engine.asearch(
        query='toxic "waste site"',
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
        filters=filters,
    )

    export_request, search_request = handler.all_json()
    assert export_request["yql"] == search_request["yql"]


async def test_export_resolves_each_collection_once(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    engine = _document_engine(http_client)
    handler.add_response({
        "root": {
            "children": [
                _export_hit("doc-1", collection_id="collection-1"),
                _export_hit("doc-2", collection_id="collection-1"),
            ]
        }
    })
    handler.add_response({
        "root": {"children": [{"fields": {"id": "collection-1", "title_attribute": "A Collection"}}]}
    })

    rows = await engine.export(
        query=None,
        limit=10,
        order_by=[],
    )

    assert handler.last_json()["ids"] == ["collection-1"]
    assert [row.collection and row.collection.title for row in rows] == ["A Collection"] * 2


async def test_export_leaves_a_document_without_a_collection_id_alone(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    Most documents belong to no collection, and must cost no lookup.

    The feeder only sets `collection_id` on a Principal that is `member_of`
    something - 9% of the corpus - and clears it to "" otherwise, which Vespa
    returns as an absent field.
    """
    engine = _document_engine(http_client)
    handler.add_response({"root": {"children": [_export_hit("doc-1")]}})

    rows = await engine.export(
        query=None,
        limit=10,
        order_by=[],
    )
    assert [row.collection for row in rows] == [None]
    assert len(handler.all_json()) == 1


async def test_export_treats_a_cleared_collection_id_as_no_collection(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """A document that has left its collection is fed `""`, not a missing field."""
    engine = _document_engine(http_client)
    handler.add_response({"root": {"children": [_export_hit("doc-1", collection_id="")]}})

    rows = await engine.export(
        query=None,
        limit=10,
        order_by=[],
    )
    assert [row.collection for row in rows] == [None]
    assert len(handler.all_json()) == 1


async def test_export_skips_the_collection_lookup_when_not_asked_for_it(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    engine = _document_engine(http_client)
    handler.add_response({
        "root": {"children": [_export_hit("doc-1", collection_id="collection-1")]}
    })

    rows = await engine.export(
        query=None,
        limit=10,
        order_by=[],
        resolve_collections=False,
    )

    assert [row.collection for row in rows] == [None]
    assert len(handler.all_json()) == 1


async def test_export_reads_labels_that_carry_no_relationship(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    Concepts are denormalised into `labels` with no `relationship`.

    Two thirds of the label elements on a real document are this shape, and
    the attribute combiner leaves the key out entirely rather than sending
    null, so requiring it rejects the whole response.
    """
    engine = _document_engine(http_client)
    handler.add_response({
        "root": {
            "children": [
                {
                    "fields": {
                        "id": "doc-1",
                        "labels": [
                            {"type": "concept", "value": "loan"},
                            {"relationship": "geography", "type": "geography", "value": "UK"},
                        ],
                    }
                }
            ]
        }
    })

    rows = await engine.export(
        query=None,
        limit=10,
        order_by=[],
    )

    labels = rows[0].document.labels
    assert [(label.relationship, label.type, label.value) for label in labels] == [
        (None, "concept", "loan"),
        ("geography", "geography", "UK"),
    ]


async def test_export_ranks_the_same_way_as_search(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    A download must come back in the order its search displayed.

    The rank profile's inputs - the topic boost above all - decide that order.
    An export that left them out would score the same documents differently and
    hand back a file whose rows are in a different order to the results on
    screen.
    """
    engine = _document_engine(http_client)
    filters = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.id", op="contains", value="concept::Q42"),
        ],
    )
    handler.add_response({"root": {"children": []}})
    handler.add_response({"root": {"children": []}})

    await engine.export(
        query="toxic",
        limit=10,
        order_by=[],
        filters=filters,
    )
    await engine.asearch(
        query="toxic",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
        filters=filters,
    )

    export_request, search_request = handler.all_json()
    ranking_inputs = {
        key: value for key, value in search_request.items() if key.startswith("input.query(")
    }
    assert ranking_inputs
    assert {k: v for k, v in export_request.items() if k.startswith("input.query(")} == ranking_inputs


async def test_export_of_a_search_that_matched_nothing_is_empty(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    """
    Vespa leaves `children` out altogether when nothing matched.

    A download of a search with no results is an empty CSV, not a 500 - and
    every other test here stubs `{"children": []}`, which is a shape Vespa
    never actually sends for a miss.
    """
    engine = _document_engine(http_client)
    handler.add_response({"root": {"fields": {"totalCount": 0}, "coverage": {"coverage": 100}}})

    rows = await engine.export(query="nothing matches this", limit=10, order_by=[])
    assert rows == []


async def test_collection_references_for_ids_that_resolve_to_nothing(
    http_client: httpx2.AsyncClient,
    handler: MockHandler,
) -> None:
    engine = _document_engine(http_client)
    handler.add_response({"root": {"fields": {"totalCount": 0}}})

    references = await engine.collection_references(["no-such-collection"])
    assert references == {}
