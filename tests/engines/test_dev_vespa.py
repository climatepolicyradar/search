from unittest.mock import patch

import pytest
from pydantic import AnyHttpUrl

from search.engines import OrderBy, Pagination, dev_vespa
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
    _document_sort_ranking_string,
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
    """The top-level passages schema's pages field lands on Passage.pages."""
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
                        "text": "some text",
                        "language": "en",
                        "type": "Text",
                        "type_confidence": 1.0,
                        "page_number": 0,
                        "pages": [5, 6],
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
            order_by=[OrderBy(field="page_number", direction="desc")],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert request_body["ranking.sorting"] == "-missing(page_number,last)"
    assert request_body["sorting.degrading"] is False


def test_passage_search_engine_order_by_wins_over_debug_mode_ranking_profile() -> None:
    """
    An explicit order_by sort overrides debug mode's ``nativerank`` profile.

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
            order_by=[OrderBy(field="page_number", direction="asc")],
        )

    request_body = mock_execute.call_args.kwargs["request_body"]
    assert request_body["ranking.profile"] == "unranked"
    assert request_body["ranking.sorting"] == "+missing(page_number,last)"


def test_passage_search_engine_reads_page_bounding_boxes_from_top_level_passages_schema() -> (
    None
):
    """The top-level passages schema's page_bounding_boxes field lands on Passage.pages_with_bounding_boxes."""
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
                        "text": "some text",
                        "language": "en",
                        "type": "Text",
                        "type_confidence": 1.0,
                        "page_number": 0,
                        "pages": [5, 6],
                        "page_bounding_boxes": [
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


def test_passage_search_engine_reads_concepts_from_top_level_passages_schema() -> None:
    """The top-level passages schema's concepts field lands on Passage.concepts."""
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
                        "text": "some text",
                        "language": "en",
                        "type": "Text",
                        "type_confidence": 1.0,
                        "page_number": 0,
                        "concepts": [
                            {
                                "id": "concept::Q1",
                                "type": "concept",
                                "value": "flooding",
                                "count": 3,
                            },
                            {
                                "id": "concept::Q2",
                                "type": "concept",
                                "value": "drought",
                                "count": 1,
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
    assert len(passage.concepts) == 2
    assert passage.concepts[0].id == "concept::Q1"
    assert passage.concepts[0].type == "concept"
    assert passage.concepts[0].value == "flooding"
    assert passage.concepts[0].count == 3
    assert passage.concepts[1].value == "drought"
    assert passage.concepts[1].count == 1
