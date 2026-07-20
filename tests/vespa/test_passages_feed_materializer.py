"""
Unit tests for ``passages_feed_materializer`` chunking.

Regression coverage for FUS-52: a single multi-hour ``vespa feed`` subprocess
over the whole passages file made connection drops late in the run expensive
(thousands of records lost, 3h+ runtime). The materializer now splits its
output into bounded chunks so each ``vespa feed`` invocation is short-lived
and a dropped connection only costs one chunk.
"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

from search.vespa import passages_feed_materializer as materializer
from search.vespa.sources.embeddings_input_v2 import TextBlock


def _text_block(idx: int) -> TextBlock:
    return {
        "language": "en",
        "type": "Text",
        "type_confidence": 1.0,
        "text": f"passage {idx}",
        "id": f"block-{idx}",
        "idx": idx,
        "pages": [],
    }


def _fake_embeddings(document_count: int, blocks_per_document: int) -> Iterator[tuple[str, dict]]:
    for doc_idx in range(document_count):
        document_id = f"doc-{doc_idx}"
        text_blocks = [
            _text_block(doc_idx * blocks_per_document + block_idx)
            for block_idx in range(blocks_per_document)
        ]
        yield document_id, {"pdf_data": {"text_blocks": text_blocks}}


def test_passages_feed_materializer_splits_output_into_chunks() -> None:
    """
    Chunk rotation with a batch/chunk-size mismatch.

    9 documents x 3 blocks = 27 passages. BATCH_SIZE=3 (every block flushes),
    CHUNK_SIZE=10 -> chunks rotate at the first flush that reaches >= 10,
    giving chunks of 12, 12, 3.
    """
    with (
        patch.object(materializer, "CHUNK_SIZE", 10),
        patch.object(materializer, "BATCH_SIZE", 3),
        patch.object(
            materializer, "_build_principal_id_lookup", return_value={}
        ),
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=_fake_embeddings(document_count=9, blocks_per_document=3),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.passages_feed_materializer()

        upload_calls = mock_s3.upload_file.call_args_list
        # 3 chunks x 2 uploads each (plain + gz)
        assert len(upload_calls) == 6

        plain_keys = [call.args[2] for call in upload_calls if call.args[2].endswith(".jsonl")]
        gz_keys = [call.args[2] for call in upload_calls if call.args[2].endswith(".jsonl.gz")]

        assert len(plain_keys) == 3
        assert len(gz_keys) == 3
        assert all(
            key.startswith("search/vespa/passages_feed_materializer/")
            for key in plain_keys
        )
        assert all(
            key.startswith("search/vespa/passages_feed_materializer_gz/")
            for key in gz_keys
        )

        plain_files = sorted(
            (call.args[0] for call in upload_calls if call.args[2].endswith(".jsonl"))
        )
        line_counts = []
        for output_file in plain_files:
            with open(output_file, "rb") as f:
                line_counts.append(sum(1 for _ in f))

        assert sorted(line_counts) == [3, 12, 12]
        assert sum(line_counts) == 27


def test_passages_feed_materializer_exact_multiple_of_chunk_size() -> None:
    """10 documents x 2 blocks = 20 passages, chunked at 10 -> exactly 2 chunks, no empty trailing chunk."""
    with (
        patch.object(materializer, "CHUNK_SIZE", 10),
        patch.object(materializer, "BATCH_SIZE", 4),
        patch.object(
            materializer, "_build_principal_id_lookup", return_value={}
        ),
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=_fake_embeddings(document_count=10, blocks_per_document=2),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.passages_feed_materializer()

        upload_calls = mock_s3.upload_file.call_args_list
        assert len(upload_calls) == 4  # 2 chunks x 2 uploads each


def test_passages_feed_materializer_no_passages_uploads_nothing() -> None:
    """Documents with no text_blocks produce zero passages and zero uploads."""
    with (
        patch.object(materializer, "CHUNK_SIZE", 10),
        patch.object(materializer, "BATCH_SIZE", 4),
        patch.object(
            materializer, "_build_principal_id_lookup", return_value={}
        ),
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=iter([("doc-0", {"pdf_data": None})]),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        materializer.passages_feed_materializer()

        assert mock_s3.upload_file.call_args_list == []
