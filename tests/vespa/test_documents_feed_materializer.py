"""Unit tests for documents_feed_materializer's passage-derived fields."""

from unittest.mock import MagicMock, patch

import orjson

from search.vespa import documents_feed_materializer as materializer
from search.vespa.sources.embeddings_input_v2 import TextBlock


def _text_block(idx: int, pages: list[dict] | None = None) -> TextBlock:
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
    """pages carries every page number; page_number keeps its first-page value."""
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
            return_value=iter(
                [("doc-0", {"pdf_data": {"text_blocks": [block]}})]
            ),
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
            if call.args[2].endswith(".jsonl") and not call.args[2].endswith(".jsonl.gz")
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
            return_value=iter(
                [("doc-0", {"pdf_data": {"text_blocks": [block]}})]
            ),
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
            if call.args[2].endswith(".jsonl") and not call.args[2].endswith(".jsonl.gz")
        )

        with open(plain_file, "rb") as f:
            update = orjson.loads(f.readline())

        passages = update["fields"]["passages"]["assign"]
        assert passages[0]["page_number"] == 0
        assert passages[0]["pages"] == []
