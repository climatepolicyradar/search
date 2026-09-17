import json
from http import HTTPStatus
from unittest.mock import Mock, patch

import pytest
from pydantic import AnyHttpUrl

from search.engines import OrderBy, Pagination, dev_vespa
from search.engines.dev_vespa import (
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
    FieldFilter,
    Filter,
    Settings,
    _document_sort_ranking_string,
    _topic_ids_from_filters,
    normalise_topic_id,
)


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


def _document_engine(**kwargs) -> DevVespaDocumentSearchEngine:
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    return DevVespaDocumentSearchEngine(settings=settings, **kwargs)


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
    engine_kwargs: dict, expected_summary: str
) -> None:
    """Every search hit summary must be one of the summaries with trimmed fields."""
    engine = _document_engine(**engine_kwargs)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["presentation.summary"] == expected_summary


def test_document_search_hits_carry_no_passages() -> None:
    """
    Search hits never carry passages, whatever Vespa returns.

    `matched-elements-only` still returns every passage that matched, which for
    numeric queries is thousands per document (~10MB a page). `/search/passages`
    is the route for passages; document hits stay lean (FUS-479).
    """
    engine = _document_engine(bolding=True)

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

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query="needle",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results[0].passages == []


def test_passage_search_engine_reads_pages_from_top_level_passages_schema() -> None:
    """The top-level passages schema's pages struct field lands on Passage.pages."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    fake_response = {
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
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results[0].pages == [5, 6]
    assert result.results[0].type == "Text"
    assert result.results[0].text == "some text"


def test_passage_search_engine_applies_order_by_to_request_body() -> None:
    """A non-empty ``order_by`` produces ``ranking.sorting`` on the Vespa request."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    fake_response = {"root": {"children": []}}

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value=fake_response
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="idx", direction="desc")],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert request_body["ranking.sorting"] == "-missing(idx,last)"
    assert request_body["sorting.degrading"] is False


def test_passage_search_engine_order_by_wins_over_debug_mode_ranking_profile() -> None:
    """
    An explicit order_by sort overrides debug mode's rank-profile choice profile.

    Matches ``DevVespaDocumentSearchEngine.search``, where sort overrides are
    always applied after any default/debug ``ranking.profile`` is set.
    """
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, debug=True)

    fake_response = {"root": {"children": []}}

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value=fake_response
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="idx", direction="asc")],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert request_body["ranking.sorting"] == "+missing(idx,last)"


def test_passage_search_engine_reads_page_bounding_boxes_from_top_level_passages_schema() -> (
    None
):
    """The top-level passages schema's pages struct field lands on Passage.pages_with_bounding_boxes."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    fake_response = {
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
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
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


def test_passage_search_engine_reads_labels_from_top_level_passages_schema() -> None:
    """The top-level passages schema's labels field lands on Passage.labels."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    fake_response = {
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
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
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


def _topic_filter_json(*topics: str, op: str = "and") -> str:
    """Filter JSON in the nested shape `_build_topic_filter` produces."""
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
    ).model_dump_json()


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


def test_document_search_engine_sends_filtered_topics_as_a_query_tensor() -> None:
    """Topics being filtered for become the topic ranking tensor."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters_json_string=_topic_filter_json("Q567", "Q1651"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == _DEFAULT_DOCUMENT_RANK_PROFILE
    assert request_body["input.query(topic_q)"] == {
        "concept::Q567": 1.0,
        "concept::Q1651": 1.0,
    }
    assert request_body["input.query(topic_weight)"] == 1.0


def test_document_search_engine_omits_topic_inputs_without_topics_filter() -> None:
    """No topic filter means no topic inputs, leaving ranking exactly as it was."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "input.query(topic_q)" not in request_body
    assert "input.query(topic_weight)" not in request_body


def test_document_search_engine_forwards_topic_weight() -> None:
    """`topic_weight=0.0` is the off switch for topic ranking."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, topic_weight=0.0)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters_json_string=_topic_filter_json("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["input.query(topic_weight)"] == 0.0
    # Surfaced for relevance-test logging rather than baked into the engine name.
    assert engine.parameters["topic_weight"] == 0.0
    assert engine.name == "DevVespaDocumentSearchEngine"


def test_document_search_engine_omits_topic_inputs_under_a_sort_override() -> None:
    """Topics ranking should be disabled when sorting by a field is specified."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="title", direction="asc")],
            filters_json_string=_topic_filter_json("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert "input.query(topic_q)" not in request_body
    assert "input.query(topic_weight)" not in request_body


def test_passage_search_engine_sends_ranking_profile_without_debug() -> None:
    """
    The rank profile is sent on every request, not just debug ones.

    Without this the live API falls through to Vespa's implicit `default`
    profile silently.
    """
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "bm25_multiplicative"


@pytest.mark.parametrize(
    ("debug", "expected_summary"),
    [(False, "search"), (True, "debug-summary")],
)
def test_passage_search_engine_requests_the_search_summary_unless_debugging(
    debug: bool, expected_summary: str
) -> None:
    """Live requests use the in-memory `search` summary; `debug=True` uses `debug-summary`."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, debug=debug)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["presentation.summary"] == expected_summary


def test_passage_search_engine_sends_filtered_topics_as_a_query_tensor() -> None:
    """Topics being filtered for become the topic ranking tensor."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters_json_string=_topic_filter_json("Q567", "Q1651"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["input.query(topic_q)"] == {
        "concept::Q567": 1.0,
        "concept::Q1651": 1.0,
    }
    assert request_body["input.query(topic_weight)"] == 1.0


def test_passage_search_engine_sends_topic_inputs_without_a_text_query() -> None:
    """
    Topic-only searches are the case topic ranking matters most for.

    Passage relevance tests routinely pass `search_terms=""`, where the topic
    score is the only signal - so the inputs must not be gated on `userQuery()`.
    """
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters_json_string=_topic_filter_json("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "userQuery()" not in request_body["yql"]
    assert request_body["input.query(topic_q)"] == {"concept::Q567": 1.0}


def test_passage_search_engine_forwards_topic_weight() -> None:
    """We can use `topic_weight=0.0` to switch off topic ranking."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings, topic_weight=0.0)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters_json_string=_topic_filter_json("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["input.query(topic_weight)"] == 0.0
    assert engine.parameters == {
        "ranking_profile": "bm25_multiplicative",
        "topic_weight": 0.0,
    }
    assert engine.name == "DevVespaPassageSearchEngine"


def test_passage_search_engine_omits_topic_inputs_under_a_sort_override() -> None:
    """Topic ranking should be disabled when sorting by a field is specified."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaPassageSearchEngine(settings=settings)

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="idx", direction="asc")],
            filters_json_string=_topic_filter_json("Q567"),
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert "input.query(topic_q)" not in request_body
    assert "input.query(topic_weight)" not in request_body


def test_document_get_renders_labels_and_concepts() -> None:
    """`get` renders a document like a search hit with labels with concepts."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings)

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
                }
            ],
        }
    }

    with patch.object(dev_vespa.requests, "get", return_value=response):
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


def _document_search_yql(engine: DevVespaDocumentSearchEngine) -> str:
    """Run a text search against a mocked Vespa and return the YQL it sent."""
    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="electric arc furnace",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    return mock_execute.call_args.kwargs["request_body"]["yql"]


def test_document_search_engine_sends_default_target_hits() -> None:
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
    engine = DevVespaDocumentSearchEngine(settings=settings)

    yql = _document_search_yql(engine)

    assert "{totalTargetHits:2000}userInput(@query)" in yql
    assert "userQuery()" not in yql
    assert engine.parameters["total_target_hits"] == 2000


def test_document_search_engine_forwards_target_hits() -> None:
    """`total_target_hits` overrides how many candidates weakAnd keeps."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings, total_target_hits=200)

    yql = _document_search_yql(engine)

    assert "{totalTargetHits:200}userInput(@query)" in yql
    # The geography and identifier arms are untouched by the change.
    assert '{defaultIndex: "geographies"}userInput(@geo_query)' in yql
    assert '{defaultIndex: "identifiers"}userInput(@query)' in yql
    assert engine.parameters["total_target_hits"] == 200


def _label_engine(**kwargs) -> DevVespaLabelSearchEngine:
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    return DevVespaLabelSearchEngine(settings=settings, **kwargs)


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
    page_token: int, page_size: int, expected_offset: int
) -> None:
    """`offset` is derived from `page_token`, not passed straight through."""
    engine = _label_engine()

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
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
    reason="order_by is a documented no-op for labels (search/engines/dev_vespa.py's "
    "DevVespaLabelSearchEngine.search()). Canary for when that changes - see "
    "test_vespa_labels_e2e.py's order_by tests for the full rationale.",
    strict=True,
    raises=AssertionError,
)
def test_label_search_engine_applies_order_by_to_request_body() -> None:
    """order_by should override ranking/sorting the way it does for passages."""
    engine = _label_engine()

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query="some",
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[OrderBy(field="value", direction="desc")],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "ranking.sorting" in request_body


def test_label_search_engine_filters_by_label_type() -> None:
    """A `label_type` argument adds a `type contains` clause to the YQL."""
    engine = _label_engine()

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            label_type="country",
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert 'type contains "country"' in request_body["yql"]


def test_label_search_engine_omits_type_clause_without_label_type() -> None:
    """No `label_type` means no `type contains` clause in the YQL."""
    engine = _label_engine()

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert "type contains" not in request_body["yql"]


def test_label_search_engine_applies_filters_json_string_to_yql() -> None:
    """`filters_json_string` is validated and folded into the YQL `where` clause."""
    engine = _label_engine()
    filters_json = json.dumps(
        {
            "op": "and",
            "filters": [{"field": "type", "op": "not_contains", "value": "keyword"}],
        }
    )

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
            filters_json_string=filters_json,
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert '!(type contains "keyword")' in request_body["yql"]


def test_label_search_engine_strips_quotes_from_query() -> None:
    """Query text is quote-stripped before being sent to Vespa (matches doc/passage engines)."""
    engine = _label_engine()

    with patch.object(
        dev_vespa, "_execute_vespa_query", return_value={"root": {"children": []}}
    ) as mock_execute:
        engine.search(
            query='"Romania"',
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["query"] == "Romania"


def test_label_search_engine_parses_valid_label_source() -> None:
    """A hit with a valid `label_source` JSON payload becomes a result label."""
    engine = _label_engine()
    label_json = json.dumps(
        {"id": "geography::Romania", "type": "geography", "value": "Romania"}
    )
    fake_response = {
        "root": {
            "children": [
                {"fields": {"label_source": label_json}},
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert len(result.results) == 1
    assert result.results[0].id == "geography::Romania"


def test_label_search_engine_skips_hits_with_malformed_label_source() -> None:
    """A hit whose `label_source` fails to parse is dropped, not raised."""
    engine = _label_engine()
    fake_response = {
        "root": {
            "children": [
                {"fields": {"label_source": "not valid json"}},
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results == []


def test_label_search_engine_skips_hits_with_empty_label_source() -> None:
    """A hit with no `label_source` field is dropped, not raised."""
    engine = _label_engine()
    fake_response = {
        "root": {
            "children": [
                {"fields": {}},
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.results == []


def test_label_search_engine_populates_debug_info_when_debugging() -> None:
    """`debug=True` records per-hit relevance/summary info on `last_debug_info`."""
    engine = _label_engine(debug=True)
    label_json = json.dumps(
        {"id": "geography::Romania", "type": "geography", "value": "Romania"}
    )
    fake_response = {
        "root": {
            "children": [
                {
                    "relevance": 0.5,
                    "fields": {
                        "label_source": label_json,
                        "value": "Romania",
                    },
                },
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert len(engine.last_debug_info) == 1
    assert engine.last_debug_info[0]["relevance"] == 0.5
    assert engine.last_debug_info[0]["value"] == "Romania"


def test_label_search_engine_omits_debug_info_by_default() -> None:
    """Without `debug=True`, no per-hit debug info is collected."""
    engine = _label_engine()
    label_json = json.dumps(
        {"id": "geography::Romania", "type": "geography", "value": "Romania"}
    )
    fake_response = {
        "root": {
            "children": [
                {"fields": {"label_source": label_json}},
            ]
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert engine.last_debug_info == []


def test_label_search_engine_reads_total_size_from_response() -> None:
    """`total_size` is read from the Vespa response's `totalCount` field."""
    engine = _label_engine()
    fake_response = {
        "root": {
            "fields": {"totalCount": 42},
            "children": [],
        }
    }

    with patch.object(dev_vespa, "_execute_vespa_query", return_value=fake_response):
        result = engine.search(
            query=None,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )

    assert result.total_size == 42
