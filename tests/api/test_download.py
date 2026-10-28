"""Unit tests for the CSV-building logic behind `/search/documents:download`."""

import csv
import io
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from api.download import (
    DEFAULT_COLUMNS,
    Column,
    build_csv_rows,
    fetch_documents_for_download,
    generate_csv,
    read_column,
    resolve_columns,
)
from search.data_in_models import (
    Document,
    DocumentRelationship,
    DocumentWithoutRelationships,
    Label,
    LabelRelationship,
)
from search.engines import ListResponse, Pagination, VespaError
from search.engines.dev_vespa import Filter


def _label(type_: str, value: str, value_type: str | None = None) -> LabelRelationship:
    value_type = value_type or type_
    return LabelRelationship(
        type=type_,
        value=Label(id=f"{value_type}::{value}", type=value_type, value=value),
        timestamp=datetime(2024, 1, 1),
    )


def _member_of(id_: str, title: str) -> DocumentRelationship:
    return DocumentRelationship(
        type="member_of",
        value=DocumentWithoutRelationships(id=id_, title=title),
    )


def test_default_columns_are_the_agreed_set_in_order() -> None:
    """
    The mapping sheet pins both the names and the order of the default set.

    URL and COLLECTION_DESCRIPTION are deliberately absent: they have no
    data behind them yet and are added, populated, by FUS-819/FUS-820.
    """
    assert [str(column) for column in DEFAULT_COLUMNS] == [
        "ID",
        "TITLE",
        "DESCRIPTION",
        "GEOGRAPHIES",
        "PUBLISHED_DATE",
        "ENTITY_TYPE",
        "CATEGORY",
        "PROVIDER",
        "COLLECTION_TITLE",
    ]


def test_url_and_collection_description_columns_are_not_present() -> None:
    """Both wait on upstream data; see FUS-819 and FUS-820."""
    assert "URL" not in set(Column)
    assert "COLLECTION_DESCRIPTION" not in set(Column)


def test_header_does_not_vary_with_the_documents_returned() -> None:
    """
    The header is the same whatever the documents happen to carry.

    The old CSV derived columns from whatever attributes and labels turned
    up, so two searches on one app could disagree.
    """
    sparse = Document(id="doc-1", title="Sparse", description=None)
    rich = Document(
        id="doc-2",
        title="Rich",
        description="Lots of metadata.",
        attributes={"published_date": "2023-10-23T00:00:00Z", "status": "published"},
        labels=[_label("category", "Law"), _label("provider", "Grantham", "agent")],
    )

    sparse_header, _ = build_csv_rows([sparse])
    rich_header, _ = build_csv_rows([rich])
    empty_header, _ = build_csv_rows([])

    assert sparse_header == rich_header == empty_header == [
        str(column) for column in DEFAULT_COLUMNS
    ]


def test_row_maps_every_column_from_its_source_field() -> None:
    doc = Document(
        id="CCLW.family.4355.0",
        title="Climate Act",
        description="An act about the climate.",
        attributes={"published_date": "2023-10-23T00:00:00Z"},
        labels=[
            _label("geography", "Uruguay", "country"),
            _label("entity_type", "National Communication (NC)"),
            _label("category", "Law"),
            _label("provider", "Grantham Research Institute", "agent"),
        ],
        documents=[_member_of("CCLW.collection.9.0", "A Collection")],
    )

    _, rows = build_csv_rows([doc])

    assert rows[0] == {
        "ID": "CCLW.family.4355.0",
        "TITLE": "Climate Act",
        "DESCRIPTION": "An act about the climate.",
        "GEOGRAPHIES": "Uruguay",
        "PUBLISHED_DATE": "2023-10-23",
        "ENTITY_TYPE": "National Communication (NC)",
        "CATEGORY": "Law",
        "PROVIDER": "Grantham Research Institute",
        "COLLECTION_TITLE": "A Collection",
    }


def test_published_date_is_formatted_as_yyyy_mm_dd() -> None:
    """The parent story requires YYYY-MM-DD, not the stored ISO timestamp."""
    doc = Document(
        id="doc-1",
        title="t",
        attributes={"published_date": "2023-10-23T00:00:00Z"},
    )

    _, rows = build_csv_rows([doc])

    assert rows[0]["PUBLISHED_DATE"] == "2023-10-23"


def test_unparsable_published_date_becomes_empty_rather_than_raising() -> None:
    doc = Document(id="doc-1", title="t", attributes={"published_date": "not a date"})

    _, rows = build_csv_rows([doc])

    assert rows[0]["PUBLISHED_DATE"] == ""


def test_multiple_geographies_are_joined() -> None:
    """
    Every geography label is kept, not just the most specific one.

    A family carries its region and its country together - Uruguay sits
    under "Latin America & Caribbean" - and the mapping names the whole
    label type.
    """
    doc = Document(
        id="doc-1",
        title="t",
        labels=[
            _label("geography", "Latin America & Caribbean", "region"),
            _label("geography", "Uruguay", "country"),
        ],
    )

    _, rows = build_csv_rows([doc])

    assert rows[0]["GEOGRAPHIES"] == "Latin America & Caribbean; Uruguay"


def test_missing_values_are_empty_strings_not_errors() -> None:
    """
    A document missing most of its metadata yields empty cells, not an error.

    This is ordinary rather than exceptional: `category::Law` and
    `category::Policy` have no `entity_type` subtype beneath them at all.
    """
    doc = Document(id="doc-1", title="Bare", description=None)

    _, rows = build_csv_rows([doc])

    assert rows[0] == {
        "ID": "doc-1",
        "TITLE": "Bare",
        "DESCRIPTION": "",
        "GEOGRAPHIES": "",
        "PUBLISHED_DATE": "",
        "ENTITY_TYPE": "",
        "CATEGORY": "",
        "PROVIDER": "",
        "COLLECTION_TITLE": "",
    }


def test_a_principal_in_no_collection_has_an_empty_collection_title() -> None:
    doc = Document(
        id="doc-1",
        title="t",
        documents=[
            DocumentRelationship(
                type="has_member",
                value=DocumentWithoutRelationships(id="doc-2", title="A member"),
            )
        ],
    )

    _, rows = build_csv_rows([doc])

    assert rows[0]["COLLECTION_TITLE"] == ""


def test_topic_and_concept_labels_never_reach_the_csv() -> None:
    """They were excluded from the old dynamic columns and stay excluded."""
    doc = Document(
        id="doc-1",
        title="t",
        labels=[
            _label("topic", "Adaptation"),
            _label("concept", "flood-risk"),
            _label("category", "Law"),
        ],
    )

    _, rows = build_csv_rows([doc])

    assert "Adaptation" not in rows[0].values()
    assert "flood-risk" not in rows[0].values()
    assert rows[0]["CATEGORY"] == "Law"


def test_freeform_attributes_cannot_inject_or_overwrite_a_column() -> None:
    """
    An attribute cannot add a column, nor overwrite one that shares its name.

    `attributes` is unvalidated freeform metadata from Vespa, so its keys
    are not a trusted vocabulary.
    """
    doc = Document(
        id="doc-1",
        title="Real Title",
        attributes={"TITLE": "sneaky", "status": "published"},
    )

    header, rows = build_csv_rows([doc])

    assert header == [str(column) for column in DEFAULT_COLUMNS]
    assert rows[0]["TITLE"] == "Real Title"
    assert "attributes.status" not in rows[0]


def test_one_row_per_document_in_order() -> None:
    docs = [
        Document(id="doc-1", title="First"),
        Document(id="doc-2", title="Second"),
        Document(id="doc-3", title="Third"),
    ]

    _, rows = build_csv_rows(docs)

    assert [row["ID"] for row in rows] == ["doc-1", "doc-2", "doc-3"]


def test_empty_documents_returns_the_header_and_no_rows() -> None:
    header, rows = build_csv_rows([])

    assert header == [str(column) for column in DEFAULT_COLUMNS]
    assert rows == []


def test_generate_csv_produces_parseable_csv_with_header_and_rows() -> None:
    docs = [
        Document(
            id="doc-1",
            title="A Climate Document",
            description="About climate.",
            attributes={"published_date": "2021-01-01T00:00:00Z"},
            labels=[_label("category", "Law")],
        ),
    ]

    csv_text = "".join(generate_csv(docs))

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert reader.fieldnames == [str(column) for column in DEFAULT_COLUMNS]
    assert rows[0]["ID"] == "doc-1"
    assert rows[0]["PUBLISHED_DATE"] == "2021-01-01"
    assert rows[0]["CATEGORY"] == "Law"


def test_generate_csv_with_no_documents_produces_just_a_header() -> None:
    csv_text = "".join(generate_csv([]))

    reader = csv.DictReader(io.StringIO(csv_text))
    assert list(reader) == []
    assert reader.fieldnames == [str(column) for column in DEFAULT_COLUMNS]


def test_every_column_can_be_read_from_a_document() -> None:
    """
    A column the API offers must never fall through.

    `read_column` matches on the column, so a column with no branch is a
    type error rather than a failure part-way through a download. This
    covers the same ground at runtime, for a document carrying none of
    the fields the columns name.
    """
    document = Document(id="doc-1", title="A Climate Document")

    for column in Column:
        assert isinstance(read_column(document, column), str), column


def test_default_columns_are_all_real_columns() -> None:
    """The fallback set cannot name a column the vocabulary lacks."""
    assert set(DEFAULT_COLUMNS) <= set(Column)


def test_no_columns_falls_back_to_the_default_set() -> None:
    """A caller that names no columns still gets a usable CSV."""
    assert resolve_columns(None) == DEFAULT_COLUMNS
    assert resolve_columns([]) == DEFAULT_COLUMNS


def test_requested_columns_determine_both_names_and_order() -> None:
    """
    The caller's order is the CSV's order, not the enum's.

    Apps want the same columns in different orders, so the header must
    follow the request rather than a fixed declaration order.
    """
    header, rows = build_csv_rows(
        [Document(id="doc-1", title="t")],
        columns=[Column.TITLE, Column.ID],
    )

    assert header == ["TITLE", "ID"]
    assert rows == [{"TITLE": "t", "ID": "doc-1"}]


def test_a_repeated_column_appears_once_in_its_first_position() -> None:
    """
    A duplicate cannot produce two identically-named columns.

    `csv.DictWriter` writes one key per field name, so a repeated column
    would emit a duplicate header and shift the remaining columns out of
    the order the caller asked for.
    """
    header, rows = build_csv_rows(
        [Document(id="doc-1", title="t")],
        columns=[Column.TITLE, Column.ID, Column.TITLE],
    )

    assert header == ["TITLE", "ID"]
    assert rows == [{"TITLE": "t", "ID": "doc-1"}]


def test_a_column_name_always_reads_the_same_source() -> None:
    """
    One name means one source, whoever asks for it.

    Apps name the same data differently, but the mapping from name to
    source is the API's and does not vary per caller - so asking for a
    column alongside different columns cannot change what it contains.
    """
    document = Document(id="doc-1", title="t")

    alone, _ = build_csv_rows([document], columns=[Column.ID])
    with_others, rows = build_csv_rows(
        [document], columns=[Column.TITLE, Column.ID]
    )

    assert alone == ["ID"]
    assert rows[0]["ID"] == "doc-1"


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


def test_fetch_combines_multiple_pages_up_to_max_results() -> None:
    """
    Pages are fetched concurrently, then reassembled in page order.

    An `internal_page_size` of 2 makes `max_results=3` span two pages
    (page 1: page_size=2, page 2: page_size=1), both dispatched up front.
    """
    engine = _make_engine([_docs("a", "b"), _docs("c")])

    results = fetch_documents_for_download(
        engine,
        query="x",
        order_by=[],
        filters=None,
        max_results=3,
        internal_page_size=2,
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
        engine, query="x", order_by=[], filters=None, max_results=200
    )

    assert [d.id for d in results] == ["a", "b"]


def test_fetch_propagates_a_page_failure() -> None:
    """
    A failed page's exception surfaces to the caller, not just its siblings.

    Pages are fetched concurrently via a thread pool; this confirms that
    doesn't swallow a `VespaError` raised by one of the underlying calls.
    """
    engine = MagicMock()
    engine.search.side_effect = VespaError("Vespa request failed", status_code=None)

    with pytest.raises(VespaError):
        fetch_documents_for_download(
            engine, query="x", order_by=[], filters=None, max_results=200
        )


def test_fetch_passes_query_filters_and_order_by_through() -> None:
    engine = _make_engine([_docs("a")])

    fetch_documents_for_download(
        engine,
        query="toxic waste",
        order_by=[],
        filters=Filter(op="and", filters=[]),
        max_results=10,
    )

    _, kwargs = engine.search.call_args
    assert kwargs["query"] == "toxic waste"
    assert kwargs["filters"] == Filter(op="and", filters=[])
    assert isinstance(kwargs["pagination"], Pagination)
