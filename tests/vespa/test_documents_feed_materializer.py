"""Unit tests for documents_feed_materializer's passage-derived fields."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import orjson

from search.vespa import documents_feed_materializer as materializer
from search.vespa.sources.embeddings_input_v2 import PageRef, TextBlock


def _text_block(idx: int, pages: list[PageRef] | None = None) -> TextBlock:
    return {
        "language": "en",
        "type": "Text",
        "type_confidence": 1.0,
        "text": f"passage {idx}",
        "id": f"block-{idx}",
        "idx": idx,
        "pages": pages if pages is not None else [],
    }


def test_documents_passages_feed_materializer_populates_pages_and_page_number() -> None:
    """Pages carries every page number; page_number keeps its first-page value."""
    block = _text_block(
        0,
        pages=[
            {"number": 3, "bounding_boxes": []},
            {"number": 4, "bounding_boxes": []},
        ],
    )

    with (
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=iter([("doc-0", {"pdf_data": {"text_blocks": [block]}})]),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.documents_passages_feed_materializer()

        upload_calls = mock_s3.upload_file.call_args_list
        plain_file = next(
            call.args[0]
            for call in upload_calls
            if call.args[2].endswith(".jsonl")
            and not call.args[2].endswith(".jsonl.gz")
        )

        with open(plain_file, "rb") as f:
            update = orjson.loads(f.readline())

        passages = update["fields"]["passages"]["assign"]
        assert passages[0]["page_number"] == 3
        assert passages[0]["pages"] == [3, 4]


def test_documents_passages_feed_materializer_defaults_when_no_pages() -> None:
    """page_number defaults to 0 and pages to an empty list when the block has no pages."""
    block = _text_block(0, pages=[])

    with (
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=iter([("doc-0", {"pdf_data": {"text_blocks": [block]}})]),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.documents_passages_feed_materializer()

        upload_calls = mock_s3.upload_file.call_args_list
        plain_file = next(
            call.args[0]
            for call in upload_calls
            if call.args[2].endswith(".jsonl")
            and not call.args[2].endswith(".jsonl.gz")
        )

        with open(plain_file, "rb") as f:
            update = orjson.loads(f.readline())

        passages = update["fields"]["passages"]["assign"]
        assert passages[0]["page_number"] == 0
        assert passages[0]["pages"] == []


def _inference_result(concept_id: str, name: str) -> dict:
    return {
        "id": concept_id,
        "name": name,
        "parent_concepts": [],
        "parent_concept_ids_flat": "",
        "model": "test-model",
        "start": 0,
        "end": 1,
        "timestamp": "2024-01-01T00:00:00",
    }


def test_documents_concepts_feed_materializer_emits_a_concept_counts_tensor(
    tmp_path: Path,
) -> None:
    """`concept_counts` mirrors `concepts[].count`, keyed by the same prefixed ids."""
    inference_input = {
        "passage-0": [
            _inference_result("Q1343", "climate finance"),
            _inference_result("Q638", "fossil fuel"),
        ],
        # Same concept twice in one passage counts twice - these are mention spans.
        "passage-1": [
            _inference_result("Q1343", "climate finance"),
            _inference_result("Q1343", "climate finance"),
        ],
    }

    with (
        patch.object(materializer, "OUTPUT_CACHE_DIR", tmp_path),
        patch.object(
            materializer,
            "read_inference_results",
            return_value=iter([("doc-0", inference_input)]),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.documents_concepts_feed_materializer()

        with open(mock_s3.upload_file.call_args.args[0], "rb") as f:
            update = orjson.loads(f.readline())

    fields = update["fields"]
    assert fields["concept_counts"]["assign"] == {
        "concept::Q1343": 3,
        "concept::Q638": 1,
    }
    assert {c["id"]: c["count"] for c in fields["concepts"]["assign"]} == fields[
        "concept_counts"
    ]["assign"]


def test_documents_principal_concepts_feed_materializer_emits_a_concept_counts_tensor(
    tmp_path: Path,
) -> None:
    """Principal documents accumulate their members' counts into the same tensor."""
    inference_inputs = [
        ("doc-0", {"passage-0": [_inference_result("Q1343", "climate finance")]}),
        ("doc-1", {"passage-0": [_inference_result("Q1343", "climate finance")]}),
    ]

    with (
        patch.object(materializer, "OUTPUT_CACHE_DIR", tmp_path),
        patch.object(
            materializer,
            "_build_principal_id_lookup",
            return_value={"doc-0": "principal-0", "doc-1": "principal-0"},
        ),
        patch.object(
            materializer, "read_inference_results", return_value=iter(inference_inputs)
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.documents_principal_concepts_feed_materializer()

        with open(mock_s3.upload_file.call_args.args[0], "rb") as f:
            update = orjson.loads(f.readline())

    assert update["update"] == "id:documents:documents::principal-0"
    assert update["fields"]["concept_counts"]["assign"] == {"concept::Q1343": 2}
