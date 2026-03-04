"""Tests for Passage model."""

from hypothesis import given

from search.document import Document
from search.passage import Passage
from tests.common_strategies import (
    huggingface_row_strategy,
    passage_data_strategy,
    passage_strategy,
)


@given(passage_data=passage_data_strategy())
def test_whether_passage_id_is_deterministic_for_same_inputs(passage_data):
    passage1 = Passage(**passage_data)
    passage2 = Passage(**passage_data)
    assert passage1.id == passage2.id
    assert isinstance(passage1.id, str)


@given(passage=passage_strategy())
def test_whether_passage_id_is_the_original_passage_id(passage):
    assert passage.id == passage.original_passage_id


@given(row=huggingface_row_strategy())
def test_whether_passage_from_huggingface_row_creates_valid_passage_with_correct_fields(
    row,
):
    passage = Passage.from_huggingface_row(row)
    assert isinstance(passage, Passage)
    assert isinstance(passage.id, str)
    assert passage.text == row["text_block.text"]
    assert passage.original_passage_id == row.get("text_block.text_block_id", "")
    assert isinstance(passage.document_id, str)
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
