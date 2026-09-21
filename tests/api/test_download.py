"""Unit tests for the CSV-building logic behind `/search/documents/download`."""

import csv
import io
from datetime import datetime
from unittest.mock import MagicMock

from api.download import (
    DEFAULT_MAX_RESULTS,
    EXCLUDED_LABEL_TYPES,
    build_csv_rows,
    fetch_documents_for_download,
    generate_csv,
)
from search.data_in_models import Document, Label, LabelRelationship
from search.engines import ListResponse, Pagination


def _label(type_: str, value_type: str, value: str) -> LabelRelationship:
    return LabelRelationship(
        type=type_,
        value=Label(id=f"{value_type}::{value}", type=value_type, value=value),
        timestamp=datetime(2024, 1, 1),
    )


def test_topic_and_concept_labels_are_excluded_from_columns_and_rows() -> None:
    doc = Document(
        id="doc-1",
        title="A Climate Document",
        description="About climate.",
        attributes={"status": "published"},
        labels=[
            _label("topic", "topic", "Adaptation"),
            _label("concept", "concept", "flood-risk"),
            _label("category", "category", "Law"),
        ],
    )

    header, rows = build_csv_rows([doc])

    assert "topic" not in header
    assert "concept" not in header
    assert "labels.category" in header
    row = rows[0]
    assert "Adaptation" not in row.values()
    assert "flood-risk" not in row.values()
    assert row["labels.category"] == "Law"


def test_excluded_label_types_are_exactly_topic_and_concept() -> None:
    assert EXCLUDED_LABEL_TYPES == {"topic", "concept"}


def test_attribute_and_label_columns_are_prefixed_to_avoid_collisions() -> None:
    """
    An attribute keyed "title" must never overwrite the real title column.

    `attributes` is unvalidated freeform metadata from Vespa, so an attribute
    key can collide with a fixed column name (or a label type). Prefixing
    attribute/label-derived columns with "attributes."/"labels." makes that
    collision structurally impossible.
    """
    doc = Document(
        id="doc-1",
        title="Real Title",
        description="About climate.",
        attributes={"title": "sneaky"},
        labels=[_label("category", "category", "Law")],
    )

    header, rows = build_csv_rows([doc])

    assert "attributes.title" in header
    assert "title" in header
    row = rows[0]
    assert row["title"] == "Real Title"
    assert row["attributes.title"] == "sneaky"


def test_empty_documents_returns_fixed_header_and_no_rows() -> None:
    header, rows = build_csv_rows([])

    assert header == ["document_id", "title", "description"]
    assert rows == []


def test_none_description_becomes_empty_string() -> None:
    doc = Document(
        id="doc-1",
        title="A Climate Document",
        description=None,
        attributes={},
        labels=[],
    )

    _, rows = build_csv_rows([doc])

    assert rows[0]["description"] == ""


def test_one_row_per_document_with_unique_ids() -> None:
    docs = [
        Document(id="doc-1", title="First", description=None),
        Document(id="doc-2", title="Second", description=None),
        Document(id="doc-3", title="Third", description=None),
    ]

    header, rows = build_csv_rows(docs)

    assert len(rows) == len(docs)
    ids = [row["document_id"] for row in rows]
    assert ids == ["doc-1", "doc-2", "doc-3"]
    assert len(set(ids)) == len(ids)


def test_generate_csv_produces_parseable_csv_with_header_and_rows() -> None:
    docs = [
        Document(
            id="doc-1",
            title="A Climate Document",
            description="About climate.",
            attributes={"status": "published"},
        ),
    ]

    csv_text = "".join(generate_csv(docs))

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert reader.fieldnames == [
        "document_id",
        "title",
        "description",
        "attributes.status",
    ]
    assert rows == [
        {
            "document_id": "doc-1",
            "title": "A Climate Document",
            "description": "About climate.",
            "attributes.status": "published",
        }
    ]


def test_generate_csv_with_no_documents_produces_just_a_header() -> None:
    csv_text = "".join(generate_csv([]))

    reader = csv.DictReader(io.StringIO(csv_text))
    assert list(reader) == []
    assert reader.fieldnames == ["document_id", "title", "description"]


def _make_engine(pages: list[list[Document]]) -> MagicMock:
    """A mock `DevVespaDocumentSearchEngine` returning `pages` in sequence."""
    engine = MagicMock()
    engine.search.side_effect = [
        ListResponse(results=page, total_size=None, next_page_token=None)
        for page in pages
    ]
    return engine


def _docs(*ids: str) -> list[Document]:
    return [Document(id=i, title=i, description=None) for i in ids]


def test_fetch_stops_once_max_results_reached(monkeypatch) -> None:
    """
    With a real internal page size, `max_results=3` is requested in one call
    (page_size=min(_INTERNAL_PAGE_SIZE, 3)=3), so a second call only happens
    if the first page is genuinely full at the *requested* size and more
    remain. Patch `_INTERNAL_PAGE_SIZE` down to 2 so:
    - call 1 requests page_size=min(2, 3)=2, mock returns 2 items (full,
      continue), page_token becomes 2
    - call 2 requests page_size=min(2, 3-2)=1, mock returns exactly 1 item
      (matches what was requested, loop's `max_results` condition then
      stops it - not the short-page rule)
    This reaches `max_results=3` in two calls without contradicting the
    short-page-means-exhausted rule the other tests in this file rely on
    (mocks must return exactly the page size the implementation will
    request at each step, not arbitrary canned pages).
    """
    monkeypatch.setattr("api.download._INTERNAL_PAGE_SIZE", 2)
    engine = _make_engine([_docs("a", "b"), _docs("c")])

    results = fetch_documents_for_download(
        engine, query="x", order_by=[], filters_json_string=None, max_results=3
    )

    assert [d.id for d in results] == ["a", "b", "c"]
    assert engine.search.call_count == 2


def test_fetch_stops_when_a_page_is_short() -> None:
    """A page shorter than requested means Vespa has no more results."""
    engine = _make_engine([_docs("a", "b")])
    engine.search.side_effect = [
        ListResponse(results=_docs("a", "b"), total_size=None, next_page_token=None),
    ]

    results = fetch_documents_for_download(
        engine, query="x", order_by=[], filters_json_string=None, max_results=100
    )

    assert [d.id for d in results] == ["a", "b"]
    assert engine.search.call_count == 1


def test_default_max_results_is_500() -> None:
    assert DEFAULT_MAX_RESULTS == 500


def test_fetch_passes_query_filters_and_order_by_through(monkeypatch) -> None:
    engine = _make_engine([_docs("a")])

    fetch_documents_for_download(
        engine,
        query="toxic waste",
        order_by=[],
        filters_json_string='{"op": "and", "filters": []}',
        max_results=10,
    )

    _, kwargs = engine.search.call_args
    assert kwargs["query"] == "toxic waste"
    assert kwargs["filters_json_string"] == '{"op": "and", "filters": []}'
    assert isinstance(kwargs["pagination"], Pagination)
