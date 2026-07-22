from unittest.mock import patch

import pytest

from search.engines import Pagination, dev_vespa
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
        vespa_endpoint="http://localhost:8080", vespa_read_token="token"
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
        vespa_endpoint="http://localhost:8080", vespa_read_token="token"
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
