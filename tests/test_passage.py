"""Tests for Passage model."""

from hypothesis import given
from knowledge_graph.identifiers import Identifier

from search.document import Document
from search.passage import Passage
from tests.common_strategies import (
    document_strategy,
    huggingface_row_strategy,
    passage_data_strategy,
    passage_strategy,
    text_strategy,
)


@given(passage_data=passage_data_strategy())
def test_whether_passage_id_is_deterministic_for_same_inputs(passage_data):
    passage1 = Passage(**passage_data)
    passage2 = Passage(**passage_data)
    assert passage1.id == passage2.id
    assert isinstance(passage1.id, Identifier)


@given(passage=passage_strategy(), new_text=text_strategy)
def test_whether_passage_id_changes_when_text_changes(passage, new_text):
    if new_text != passage.text:
        passage_with_new_text = passage.model_copy(update={"text": new_text})
        assert passage.id != passage_with_new_text.id


@given(passage=passage_strategy(), new_doc=document_strategy())
def test_whether_passage_id_changes_when_document_id_changes(passage, new_doc):
    if passage.document_id != new_doc.id:
        passage_with_new_doc = passage.model_copy(update={"document_id": new_doc.id})
        assert passage.id != passage_with_new_doc.id


@given(passage=passage_strategy())
def test_whether_passage_id_is_invariant_to_original_passage_id_and_labels(passage):
    base_id = passage.id
    passage_with_different_original_id = passage.model_copy(
        update={"original_passage_id": "different"}
    )
    assert passage_with_different_original_id.id == base_id


@given(row=huggingface_row_strategy())
def test_whether_passage_from_huggingface_row_creates_valid_passage_with_correct_fields(
    row,
):
    passage = Passage.from_huggingface_row(row)
    assert isinstance(passage, Passage)
    assert isinstance(passage.id, Identifier)
    assert passage.text == row["text_block.text"]
    assert passage.original_passage_id == row.get("text_block.text_block_id", "")
    assert isinstance(passage.document_id, Identifier)
    assert passage.labels == []


@given(row=huggingface_row_strategy())
def test_passage_document_id_matches_document_from_same_row(row):
    passage = Passage.from_huggingface_row(row)
    expected_doc = Document.from_huggingface_row(row)
    assert passage.document_id == expected_doc.id


@given(row=huggingface_row_strategy(include_text_block_id=False))
def test_whether_passage_from_huggingface_row_uses_empty_string_when_text_block_id_missing(
    row,
):
    passage = Passage.from_huggingface_row(row)
    assert passage.original_passage_id == ""


@given(row=huggingface_row_strategy(include_text_block=False))
def test_whether_passage_from_huggingface_row_raises_key_error_when_text_missing(row):
    try:
        Passage.from_huggingface_row(row)
        assert False, "Expected KeyError"
    except KeyError as e:
        assert "text_block.text" in str(e)


@given(row=huggingface_row_strategy(include_source_url=False))
def test_whether_passage_from_huggingface_row_raises_key_error_when_source_url_missing(
    row,
):
    try:
        Passage.from_huggingface_row(row)
        assert False, "Expected KeyError"
    except KeyError as e:
        assert "document_metadata.source_url" in str(e)
