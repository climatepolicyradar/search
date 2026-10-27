"""Unit tests for the CSV-building logic behind `/search/documents:download`."""

import csv
import io
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from api.download import (
    DEFAULT_SCHEMA,
    SCHEMAS,
    Theme,
    build_csv_rows,
    fetch_documents_for_download,
    generate_csv,
    schema_for_theme,
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


def test_header_is_the_agreed_fixed_column_set_in_order() -> None:
    """
    The mapping sheet pins both the names and the order.

    URL and COLLECTION_DESCRIPTION are deliberately absent: they have no
    data behind them yet and are added, populated, by FUS-819/FUS-820.
    """
    assert list(DEFAULT_SCHEMA) == [
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
    assert "URL" not in list(DEFAULT_SCHEMA)
    assert "COLLECTION_DESCRIPTION" not in list(DEFAULT_SCHEMA)


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

    assert sparse_header == rich_header == empty_header == list(DEFAULT_SCHEMA)


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

    assert header == list(DEFAULT_SCHEMA)
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

    assert header == list(DEFAULT_SCHEMA)
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
    assert reader.fieldnames == list(DEFAULT_SCHEMA)
    assert rows[0]["ID"] == "doc-1"
    assert rows[0]["PUBLISHED_DATE"] == "2021-01-01"
    assert rows[0]["CATEGORY"] == "Law"


def test_generate_csv_with_no_documents_produces_just_a_header() -> None:
    csv_text = "".join(generate_csv([]))

    reader = csv.DictReader(io.StringIO(csv_text))
    assert list(reader) == []
    assert reader.fieldnames == list(DEFAULT_SCHEMA)


def test_cpr_cclw_and_mcf_share_one_schema() -> None:
    """
    They happen to want identical columns, so they resolve to one object.

    This is a fact about the current mapping, not a constraint: giving any
    of them its own columns means adding an entry to `SCHEMAS`.
    """
    assert schema_for_theme(Theme.CPR) is schema_for_theme(Theme.CCLW)
    assert schema_for_theme(Theme.CCLW) is schema_for_theme(Theme.MCF)
    assert schema_for_theme(Theme.CPR) is DEFAULT_SCHEMA


def test_every_theme_resolves_to_a_schema() -> None:
    """A theme the API accepts must never fall through to a KeyError."""
    for theme in Theme:
        assert theme in SCHEMAS


def test_an_unknown_theme_falls_back_to_the_default_schema() -> None:
    """A caller that sends no theme, or a stale one, still gets a CSV."""
    assert schema_for_theme(None) is DEFAULT_SCHEMA


def test_theme_selects_the_header(monkeypatch) -> None:
    """`build_csv_rows` emits the columns of the theme it is given."""
    narrow = {"ID": lambda document: document.id}
    monkeypatch.setitem(SCHEMAS, Theme.CPR, narrow)

    header, rows = build_csv_rows(
        [Document(id="doc-1", title="t")], theme=Theme.CPR
    )

    assert header == ["ID"]
    assert rows == [{"ID": "doc-1"}]


def test_schema_columns_determine_both_names_and_order() -> None:
    """
    A schema is an ordered mapping, so one declaration pins both.

    CCC needs different columns in a different order, so the two must not
    drift apart into a separate name list and order list.
    """
    header, _ = build_csv_rows([])
    assert header == list(DEFAULT_SCHEMA)


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


########################################################################
# CCC (FUS-675)
########################################################################


def _legal_concept(label_type: str, value: str) -> LabelRelationship:
    """
    A CCC legal concept label.

    `jurisdiction`, `principal_law` and `case_category` all arrive under the
    one `legal_concept` relationship and are told apart only by the type on
    the label itself, which is what gives each its own column.
    """
    return _label("legal_concept", value, label_type)


def _ccc_header() -> list[str]:
    return list(SCHEMAS[Theme.CCC])


def test_ccc_header_is_the_agreed_fixed_column_set_in_order() -> None:
    """
    The CCC mapping tab pins both the names and the order.

    URL and BUNDLE_URL are deliberately absent: BUNDLE_URL cannot be built
    here at all (no collection slug exists in Vespa), so FUS-819 inserts
    both rather than filling them.
    """
    assert _ccc_header() == [
        "ID",
        "TITLE",
        "DESCRIPTION",
        "BUNDLE_ID",
        "BUNDLE_TITLE",
        "GEOGRAPHIES",
        "PUBLISHED_DATE",
        "CASE_STATUS",
        "CASE_NUMBER",
        "AT_ISSUE",
        "ORIGINAL_CASE_NAME",
        "PRINCIPAL_LAWS",
        "CASE_CATEGORIES",
        "JURISDICTIONS",
    ]


def test_ccc_url_and_bundle_url_columns_are_not_present() -> None:
    """Both wait on upstream `items[]` population; see FUS-819."""
    assert "URL" not in _ccc_header()
    assert "BUNDLE_URL" not in _ccc_header()


def test_ccc_has_its_own_schema_distinct_from_the_default() -> None:
    assert schema_for_theme(Theme.CCC) is not DEFAULT_SCHEMA


def test_ccc_drops_the_family_and_document_level_columns() -> None:
    """
    CCC is a case-level download, so the shared columns do not apply.

    ENTITY_TYPE, CATEGORY and PROVIDER are constant across every case on
    CCC, and COLLECTION_TITLE is named BUNDLE_TITLE here.
    """
    for column in ("ENTITY_TYPE", "CATEGORY", "PROVIDER", "COLLECTION_TITLE"):
        assert column not in _ccc_header()


def test_ccc_row_maps_every_column_from_its_source_field() -> None:
    """A fully populated case, shaped as production data-in documents are."""
    doc = Document(
        id="Sabin.family.17068.0",
        title="Public Ministry vs. State of Rio Grande do Sul",
        description="A case about a carbochemical complex.",
        attributes={
            "published_date": "2019-01-01T00:00:00Z",
            "case_status": "Decided",
            "identifier::case_number": "9065931-65.2019.8.21.0001",
            "core_object": "The Public Prosecutor's Office seeks a declaration.",
            "original_case_name": "Ministerio Publico vs. Estado do Rio Grande do Sul",
        },
        labels=[
            _label("status", "Principal"),
            _label("geography", "Brazil", "country"),
            _legal_concept("jurisdiction", "Brazil"),
            _legal_concept("principal_law", "Federal Constitution of 1988"),
            _legal_concept("case_category", "Suits against governments"),
        ],
        documents=[_member_of("Sabin.collection.3358.0", "A Bundle")],
    )

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert rows[0] == {
        "ID": "Sabin.family.17068.0",
        "TITLE": "Public Ministry vs. State of Rio Grande do Sul",
        "DESCRIPTION": "A case about a carbochemical complex.",
        "BUNDLE_ID": "Sabin.collection.3358.0",
        "BUNDLE_TITLE": "A Bundle",
        "GEOGRAPHIES": "Brazil",
        "PUBLISHED_DATE": "2019-01-01",
        "CASE_STATUS": "Decided",
        "CASE_NUMBER": "9065931-65.2019.8.21.0001",
        "AT_ISSUE": "The Public Prosecutor's Office seeks a declaration.",
        "ORIGINAL_CASE_NAME": "Ministerio Publico vs. Estado do Rio Grande do Sul",
        "PRINCIPAL_LAWS": "Federal Constitution of 1988",
        "CASE_CATEGORIES": "Suits against governments",
        "JURISDICTIONS": "Brazil",
    }


def test_ccc_legal_concepts_are_split_by_label_type_not_relationship() -> None:
    """
    The three legal-concept columns must not bleed into one another.

    `jurisdiction`, `principal_law` and `case_category` share the single
    `legal_concept` relationship in production, so reading them by
    relationship would put all of them in all three cells.
    """
    doc = Document(
        id="doc-1",
        title="t",
        labels=[
            _legal_concept("jurisdiction", "Brazil"),
            _legal_concept("jurisdiction", "Rio Grande do Sul State Court"),
            _legal_concept("principal_law", "Federal Constitution of 1988"),
            _legal_concept("case_category", "Suits against governments"),
        ],
    )

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert rows[0]["JURISDICTIONS"] == "Brazil; Rio Grande do Sul State Court"
    assert rows[0]["PRINCIPAL_LAWS"] == "Federal Constitution of 1988"
    assert rows[0]["CASE_CATEGORIES"] == "Suits against governments"


def test_ccc_case_status_ignores_the_principal_status_label() -> None:
    """
    Every case carries `status::Principal` alongside its real case status.

    CASE_STATUS therefore comes from the `case_status` attribute; reading
    the `status` relationship would yield "Principal; Decided".
    """
    doc = Document(
        id="doc-1",
        title="t",
        attributes={"case_status": "Decided"},
        labels=[_label("status", "Principal"), _label("status", "Decided")],
    )

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert rows[0]["CASE_STATUS"] == "Decided"


def test_ccc_multiple_principal_laws_are_joined() -> None:
    """A case commonly cites several laws; the mapping gives them one cell."""
    doc = Document(
        id="doc-1",
        title="t",
        labels=[
            _legal_concept("principal_law", "CONAMA Resolution No. 01/86"),
            _legal_concept("principal_law", "Federal Constitution of 1988"),
        ],
    )

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert (
        rows[0]["PRINCIPAL_LAWS"]
        == "CONAMA Resolution No. 01/86; Federal Constitution of 1988"
    )


def test_ccc_case_not_in_a_bundle_has_empty_bundle_columns() -> None:
    """
    About a third of cases belong to no bundle, which is not an error.

    `has_member` points at the case's own documents, not a bundle, so it
    must not be mistaken for one.
    """
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

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert rows[0]["BUNDLE_ID"] == ""
    assert rows[0]["BUNDLE_TITLE"] == ""


def test_ccc_missing_values_are_empty_strings_not_errors() -> None:
    """
    AC5: a case with no value for a field gives an empty cell, not an error.

    This is ordinary rather than exceptional - AT_ISSUE is populated on
    roughly a third of cases and ORIGINAL_CASE_NAME on a tenth.
    """
    doc = Document(id="doc-1", title="Bare", description=None)

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert rows[0] == {
        "ID": "doc-1",
        "TITLE": "Bare",
        "DESCRIPTION": "",
        "BUNDLE_ID": "",
        "BUNDLE_TITLE": "",
        "GEOGRAPHIES": "",
        "PUBLISHED_DATE": "",
        "CASE_STATUS": "",
        "CASE_NUMBER": "",
        "AT_ISSUE": "",
        "ORIGINAL_CASE_NAME": "",
        "PRINCIPAL_LAWS": "",
        "CASE_CATEGORIES": "",
        "JURISDICTIONS": "",
    }


def test_ccc_non_string_attribute_does_not_break_a_cell() -> None:
    """
    `attributes` values may be numbers or booleans, and cells are text.

    Every CCC attribute the schema reads is a string in production; this
    guards the freeform `attributes` map, which is not a trusted
    vocabulary, against putting a non-string into the CSV writer.
    """
    doc = Document(id="doc-1", title="t", attributes={"case_status": True})

    _, rows = build_csv_rows([doc], theme=Theme.CCC)

    assert rows[0]["CASE_STATUS"] == "True"


def test_ccc_generate_csv_produces_parseable_csv_with_header_and_rows() -> None:
    docs = [
        Document(
            id="Sabin.family.1.0",
            title="A Case",
            attributes={
                "published_date": "2021-01-01T00:00:00Z",
                "case_status": "Filed",
            },
            labels=[_legal_concept("jurisdiction", "Brazil")],
        ),
    ]

    csv_text = "".join(generate_csv(docs, theme=Theme.CCC))

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert reader.fieldnames == _ccc_header()
    assert rows[0]["ID"] == "Sabin.family.1.0"
    assert rows[0]["PUBLISHED_DATE"] == "2021-01-01"
    assert rows[0]["CASE_STATUS"] == "Filed"
    assert rows[0]["JURISDICTIONS"] == "Brazil"


def test_ccc_does_not_change_the_other_themes() -> None:
    """Giving CCC its own columns must leave CPR/CCLW/MCF untouched."""
    assert schema_for_theme(Theme.CPR) is DEFAULT_SCHEMA
    assert schema_for_theme(Theme.CCLW) is DEFAULT_SCHEMA
    assert schema_for_theme(Theme.MCF) is DEFAULT_SCHEMA
