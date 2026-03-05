"""Tests for Document model."""

from hypothesis import given
from pydantic import AnyHttpUrl

from search.document import Document
from tests.common_strategies import (
    document_data_strategy,
    document_strategy,
    huggingface_row_strategy,
)


@given(document_data=document_data_strategy())
def test_whether_document_id_is_deterministic_for_same_inputs(document_data):
    doc1 = Document(**document_data)
    doc2 = Document(**document_data)
    assert doc1.id == doc2.id
    assert isinstance(doc1.id, str)


@given(doc=document_strategy())
def test_whether_document_id_is_the_original_document_id(doc):
    assert doc.id == doc.original_document_id


@given(row=huggingface_row_strategy())
def test_whether_document_from_huggingface_row_creates_valid_document_with_correct_fields(
    row,
):
    doc = Document.from_huggingface_row(row)
    assert isinstance(doc, Document)
    assert isinstance(doc.id, str)
    assert str(doc.source_url) == str(AnyHttpUrl(row["document_metadata.source_url"]))
    assert doc.description == row["document_metadata.description"]
    assert doc.original_document_id == row["document_id"]
    assert doc.id == row["document_id"]
    assert doc.labels == []


def test_whether_document_from_huggingface_row_raises_key_error_when_source_url_missing():
    row = {"document_metadata.document_title": "Test", "document_id": "doc-123"}
    try:
        Document.from_huggingface_row(row)
        assert False, "Expected KeyError"
    except KeyError as e:
        assert "document_metadata.source_url" in str(e)
