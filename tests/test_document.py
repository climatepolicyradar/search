"""Tests for Document model."""

from hypothesis import given
from knowledge_graph.identifiers import Identifier
from pydantic import AnyHttpUrl

from search.document import Document
from tests.common_strategies import (
    document_data_strategy,
    document_strategy,
    huggingface_row_strategy,
    text_strategy,
    url_strategy,
)


@given(document_data=document_data_strategy())
def test_whether_document_id_is_deterministic_for_same_inputs(document_data):
    doc1 = Document(**document_data)
    doc2 = Document(**document_data)
    assert doc1.id == doc2.id
    assert isinstance(doc1.id, Identifier)


@given(doc=document_strategy(), new_title=text_strategy)
def test_whether_document_id_changes_when_title_changes(doc, new_title):
    if new_title != doc.title:
        doc_with_new_title = doc.model_copy(update={"title": new_title})
        assert doc.id != doc_with_new_title.id


@given(doc=document_strategy(), new_url=url_strategy)
def test_whether_document_id_changes_when_source_url_changes(doc, new_url):
    if str(doc.source_url).lower() != str(new_url).lower():
        doc_with_new_url = doc.model_copy(update={"source_url": new_url})
        assert doc.id != doc_with_new_url.id


@given(doc=document_strategy())
def test_whether_document_id_is_invariant_to_description_original_document_id_and_labels(
    doc,
):
    base_id = doc.id
    doc_with_different_description = doc.model_copy(update={"description": "Different"})
    assert doc_with_different_description.id == base_id
    doc_with_different_original_id = doc.model_copy(
        update={"original_document_id": "different"}
    )
    assert doc_with_different_original_id.id == base_id
    doc_with_all_different_non_id_fields = doc.model_copy(
        update={"description": "Different", "original_document_id": "different"}
    )
    assert doc_with_all_different_non_id_fields.id == base_id


@given(row=huggingface_row_strategy())
def test_whether_document_from_huggingface_row_creates_valid_document_with_correct_fields(
    row,
):
    doc = Document.from_huggingface_row(row)
    assert isinstance(doc, Document)
    assert isinstance(doc.id, Identifier)
    assert str(doc.source_url) == str(AnyHttpUrl(row["document_metadata.source_url"]))
    assert doc.description == row["document_metadata.description"]
    assert doc.original_document_id == row["document_id"]
    assert doc.labels == []


def test_whether_document_from_huggingface_row_raises_key_error_when_source_url_missing():
    row = {"document_metadata.document_title": "Test", "document_id": "doc-123"}
    try:
        Document.from_huggingface_row(row)
        assert False, "Expected KeyError"
    except KeyError as e:
        assert "document_metadata.source_url" in str(e)
