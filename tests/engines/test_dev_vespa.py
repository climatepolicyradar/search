from unittest.mock import patch

import pytest
from pydantic import AnyHttpUrl

from search.engines import OrderBy, Pagination, dev_vespa
from search.engines.dev_vespa import (
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    DevVespaDocumentSearchEngine,
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


def test_document_search_engine_reads_pages_from_embedded_passage_struct() -> None:
    """The embedded documents.passages struct's pages field lands on Passage.pages."""
    settings = Settings(
        vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
        vespa_read_token="test-read-token",  # nosec B106
    )
    engine = DevVespaDocumentSearchEngine(settings=settings)

    fake_response = {
        "root": {
            "children": [
                {
                    "id": "id:documents:documents::doc-0",
                    "fields": {
                        "document_source": (
                            '{"id": "doc-0", "labels": [], "documents": []}'
                        ),
                        "passages": [
                            {
                                "text_block_id": "block-0",
                                "idx": 0,
                                "language": "en",
                                "type": "Text",
                                "type_confidence": 1.0,
                                "page_number": 3,
                                "pages": [3, 4],
                                "heading_id": None,
                            }
                        ],
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

    assert result.results[0].passages[0].pages == [3, 4]


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
    assert engine.parameters == {
        "ranking_profile": _DEFAULT_DOCUMENT_RANK_PROFILE,
        "topic_weight": 0.0,
    }
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
