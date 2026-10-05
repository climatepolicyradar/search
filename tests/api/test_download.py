"""Unit tests for the CSV-building logic behind `/search/documents:download`."""

import csv
import io
from collections.abc import Iterator
from datetime import datetime
from typing import NamedTuple, get_args
from unittest.mock import MagicMock

import pytest

from api.download import (
    DEFAULT_MAX_RESULTS,
    EXCLUDED_LABEL_TYPES,
    build_csv_rows,
    fetch_documents_for_download,
    generate_csv,
    generate_templated_csv,
)
from api.download_templates import (
    CSV_TEMPLATES,
    TemplateName,
    attributes_field,
    field,
    labels_field,
)
from search.data_in_models import Document, Label, LabelRelationship
from search.engines import ListResponse, Pagination, VespaError


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


class _ParsedCsv(NamedTuple):
    fieldnames: list[str]
    rows: list[dict[str, str]]


def _parse(chunks: Iterator[str]) -> _ParsedCsv:
    """Parse generated CSV chunks back into its header and rows."""
    reader = csv.DictReader(io.StringIO("".join(chunks)))
    rows = list(reader)
    return _ParsedCsv(fieldnames=list(reader.fieldnames or []), rows=rows)


def test_generate_templated_csv_applies_the_template_to_each_document() -> None:
    """Columns are the template's keys, cells its funcs, both in its order."""
    template = {
        "identifier": field("id"),
        "name": field("title"),
        "categories": labels_field("category"),
    }
    docs = [
        Document(
            id="doc-1",
            title="First",
            labels=[_label("has_category", "category", "Law")],
        ),
        Document(id="doc-2", title="Second"),
    ]

    csv_text = "".join(generate_templated_csv(docs, template))

    reader = csv.DictReader(io.StringIO(csv_text))
    assert reader.fieldnames == ["identifier", "name", "categories"]
    assert list(reader) == [
        {"identifier": "doc-1", "name": "First", "categories": "Law"},
        {"identifier": "doc-2", "name": "Second", "categories": ""},
    ]


def test_templated_csv_columns_do_not_vary_with_the_documents() -> None:
    """
    The point of a template: one fixed shape, whatever the results hold.

    `build_csv_rows` derives its columns from the attributes and label types
    the result set happens to carry, so two searches can return two different
    shapes. A template fixes them, so a downstream parser can rely on the
    header - an absent value is an empty cell, not a missing column, and an
    attribute nobody asked for stays out entirely.
    """
    template = {"identifier": field("id"), "status": attributes_field("status")}
    sparse = Document(id="doc-1", title="First")
    rich = Document(
        id="doc-2",
        title="Second",
        attributes={"status": "published", "unasked_for": "extra"},
        labels=[_label("has_category", "category", "Law")],
    )

    sparse_rows = _parse(generate_templated_csv([sparse], template))
    rich_rows = _parse(generate_templated_csv([rich], template))

    assert sparse_rows.fieldnames == rich_rows.fieldnames == ["identifier", "status"]
    assert sparse_rows.rows == [{"identifier": "doc-1", "status": ""}]
    assert rich_rows.rows == [{"identifier": "doc-2", "status": "published"}]


def test_generate_templated_csv_with_no_documents_produces_just_a_header() -> None:
    template = {"identifier": field("id")}

    parsed = _parse(generate_templated_csv([], template))

    assert parsed.fieldnames == ["identifier"]
    assert parsed.rows == []


def test_every_template_name_resolves_to_a_template() -> None:
    """
    `TemplateName` is the API surface and `CSV_TEMPLATES` the implementation.

    A name in the `Literal` with no entry in the registry passes validation
    and then `KeyError`s into a 500; an entry with no name is unreachable.
    """
    assert set(CSV_TEMPLATES) == set(get_args(TemplateName))


def _make_engine(pages: list[list[Document]]) -> MagicMock:
    """
    A mock `DevVespaDocumentSearchEngine` returning `pages[page_token - 1]`.

    Pages are fetched concurrently by the implementation, so responses are
    keyed by the requested `page_token` (not by call order) to stay
    deterministic regardless of thread scheduling.
    """
    engine = MagicMock()

    def search(**kwargs):
        page_token = kwargs["pagination"].page_token
        return ListResponse(
            results=pages[page_token - 1], total_size=None, next_page_token=None
        )

    engine.search.side_effect = search
    return engine


def _docs(*ids: str) -> list[Document]:
    return [Document(id=i, title=i, description=None) for i in ids]


def test_fetch_combines_multiple_pages_up_to_max_results(monkeypatch) -> None:
    """
    Pages are fetched concurrently, then reassembled in page order.

    Patch `_INTERNAL_PAGE_SIZE` down to 2 so `max_results=3` spans two pages
    (page 1: page_size=2, page 2: page_size=1), both dispatched up front.
    """
    monkeypatch.setattr("api.download._INTERNAL_PAGE_SIZE", 2)
    engine = _make_engine([_docs("a", "b"), _docs("c")])

    results = fetch_documents_for_download(
        engine, query="x", order_by=[], filters_json_string=None, max_results=3
    )

    assert [d.id for d in results] == ["a", "b", "c"]
    assert engine.search.call_count == 2


def test_fetch_truncates_after_a_short_page() -> None:
    """
    A page shorter than requested means Vespa has no more results.

    Results from any page after the short one are discarded, even though
    every page is dispatched concurrently up front.
    """
    engine = _make_engine([_docs("a", "b"), _docs("c")])

    results = fetch_documents_for_download(
        engine, query="x", order_by=[], filters_json_string=None, max_results=200
    )

    assert [d.id for d in results] == ["a", "b"]


def test_fetch_propagates_a_page_failure() -> None:
    """
    A failed page's exception surfaces to the caller, not just its siblings.

    Pages are fetched concurrently via a thread pool; this confirms that
    doesn't swallow a `VespaError` raised by one of the underlying calls.
    """
    engine = MagicMock()
    engine.search.side_effect = VespaError("Vespa request failed")

    with pytest.raises(VespaError):
        fetch_documents_for_download(
            engine, query="x", order_by=[], filters_json_string=None, max_results=200
        )


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
