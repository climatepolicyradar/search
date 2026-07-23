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
            materializer, "_build_passage_concepts_lookup", return_value={}
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
            materializer, "_build_passage_concepts_lookup", return_value={}
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
            materializer, "_build_passage_concepts_lookup", return_value={}
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


def test_passages_feed_materializer_aborts_without_uploading_on_exception() -> None:
    """
    An exception mid-run must not upload the in-progress final chunk.

    Matches `documents_feed_materializer`'s behaviour, where the upload only
    happens after the write loop completes without error.
    """

    def _raising_embeddings() -> Iterator[tuple[str, dict]]:
        yield from _fake_embeddings(document_count=1, blocks_per_document=1)
        raise RuntimeError("boom")

    with (
        patch.object(materializer, "CHUNK_SIZE", 10),
        patch.object(materializer, "BATCH_SIZE", 1),
        patch.object(
            materializer, "_build_principal_id_lookup", return_value={}
        ),
        patch.object(
            materializer, "_build_passage_concepts_lookup", return_value={}
        ),
        patch.object(
            materializer,
            "read_embeddings_input_v2",
            return_value=_raising_embeddings(),
        ),
        patch.object(materializer.boto3, "client") as mock_boto_client,
    ):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        try:
            materializer.passages_feed_materializer()
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError to propagate")

        assert mock_s3.upload_file.call_args_list == []

def test_heading_text_resolved_from_heading_id() -> None:
    """heading_text is resolved to the text of the block that heading_id points at."""
    heading = _text_block(0)
    heading["id"] = "heading-1"
    heading["text"] = "Chapter 1: Introduction"

    passage = _text_block(1)
    passage["id"] = "passage-1"
    passage["heading_id"] = "heading-1"

    block_text_by_id = {
        heading["id"]: heading["text"],
        passage["id"]: passage["text"],
    }

    update = materializer._text_block_to_vespa_update(
        passage, "doc-0", block_text_by_id=block_text_by_id
    )
    fields = update["fields"]

    assert fields.get("heading_id") == {"assign": "heading-1"}
    assert fields.get("heading_text") == {"assign": "Chapter 1: Introduction"}

def _inference_result(concept_id: str, name: str) -> dict:
    return {
        "id": concept_id,
        "name": name,
        "parent_concepts": [],
        "parent_concept_ids_flat": "",
        "model": "test-model",
        "start": 0,
        "end": 1,
        "timestamp": "2024-01-01T00:00:00Z",
    }


def test_build_passage_concepts_lookup_aggregates_per_passage() -> None:
    """Repeated hits of a concept in a passage collapse to one entry with a count."""
    inference = [
        (
            "doc-0",
            {
                "block-0": [
                    _inference_result("Q1", "flooding"),
                    _inference_result("Q1", "flooding"),
                    _inference_result("Q2", "drought"),
                ],
                "block-1": [_inference_result("Q2", "drought")],
            },
        )
    ]
    with patch.object(
        materializer, "read_inference_results", return_value=iter(inference)
    ):
        lookup = materializer._build_passage_concepts_lookup()

    assert lookup["block-0"] == [
        {"id": "concept::Q1", "type": "concept", "value": "flooding", "count": 2},
        {"id": "concept::Q2", "type": "concept", "value": "drought", "count": 1},
    ]
    assert lookup["block-1"] == [
        {"id": "concept::Q2", "type": "concept", "value": "drought", "count": 1},
    ]


def test_text_block_to_vespa_update_includes_and_omits_concepts() -> None:
    """Concepts are assigned when present, and the key is absent when there are none."""
    concepts: list[materializer.VespaConceptField] = [
        {"id": "concept::Q1", "type": "concept", "value": "flooding", "count": 2}
    ]
    with_concepts = materializer._text_block_to_vespa_update(
        _text_block(0), "doc-0", concepts=concepts
    )
    assert with_concepts["fields"].get("concepts") == {"assign": concepts}

    without_concepts = materializer._text_block_to_vespa_update(_text_block(0), "doc-0")
    assert "concepts" not in without_concepts["fields"]


def test_text_block_to_vespa_update_includes_pages_from_multi_page_block() -> None:
    """Pages is assigned as the full list of page numbers, not just the first."""
    block = _text_block(0)
    block["pages"] = [
        {"number": 3, "bounding_boxes": []},
        {"number": 4, "bounding_boxes": []},
    ]

    update = materializer._text_block_to_vespa_update(block, "doc-0")

    assert update["fields"].get("pages") == {"assign": [3, 4]}


def test_text_block_to_vespa_update_omits_pages_when_block_has_none() -> None:
    """Pages is absent from the update when the source block has no pages."""
    update = materializer._text_block_to_vespa_update(_text_block(0), "doc-0")

    assert "pages" not in update["fields"]


def test_text_block_to_vespa_update_includes_page_bounding_boxes() -> None:
    """page_bounding_boxes carries every page's boxes and coordinates."""
    block = _text_block(0)
    block["pages"] = [
        {
            "number": 3,
            "bounding_boxes": [
                {"coordinates": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]},
            ],
        },
        {
            "number": 4,
            "bounding_boxes": [
                {"coordinates": [{"x": 0.5, "y": 0.6}]},
                {"coordinates": [{"x": 0.7, "y": 0.8}]},
            ],
        },
    ]

    update = materializer._text_block_to_vespa_update(block, "doc-0")

    assert update["fields"].get("page_bounding_boxes") == {
        "assign": [
            {
                "number": 3,
                "bounding_boxes": [
                    {"coordinates": [{"x": 0.1, "y": 0.2}, {"x": 0.3, "y": 0.4}]},
                ],
            },
            {
                "number": 4,
                "bounding_boxes": [
                    {"coordinates": [{"x": 0.5, "y": 0.6}]},
                    {"coordinates": [{"x": 0.7, "y": 0.8}]},
                ],
            },
        ]
    }


def test_text_block_to_vespa_update_omits_page_bounding_boxes_when_block_has_none() -> None:
    """page_bounding_boxes is absent from the update when the block has no pages."""
    update = materializer._text_block_to_vespa_update(_text_block(0), "doc-0")

    assert "page_bounding_boxes" not in update["fields"]


class TestChunkWriter:
    """Unit tests for `_ChunkWriter` in isolation, no embeddings/S3 mocking needed."""

    def test_rotates_and_uploads_at_chunk_boundary(self) -> None:
        with (
            patch.object(materializer, "CHUNK_SIZE", 4),
            patch.object(materializer, "BATCH_SIZE", 2),
        ):
            mock_s3 = MagicMock()
            writer = materializer._ChunkWriter(s3=mock_s3)

            for i in range(6):
                writer.append(f"line-{i}\n".encode())

            writer.close()

            assert writer.total == 6
            assert writer.chunks_uploaded == 2  # one rotation at 4, one final at close()
            assert mock_s3.upload_file.call_count == 4  # 2 chunks x (plain + gz)

    def test_close_is_a_noop_upload_when_buffer_lands_on_boundary(self) -> None:
        with (
            patch.object(materializer, "CHUNK_SIZE", 4),
            patch.object(materializer, "BATCH_SIZE", 2),
        ):
            mock_s3 = MagicMock()
            writer = materializer._ChunkWriter(s3=mock_s3)

            for i in range(4):
                writer.append(f"line-{i}\n".encode())
            writer.close()

            assert writer.total == 4
            assert writer.chunks_uploaded == 1  # only the mid-run rotation
            assert mock_s3.upload_file.call_count == 2  # 1 chunk x (plain + gz)

    def test_abort_does_not_upload(self) -> None:
        with (
            patch.object(materializer, "CHUNK_SIZE", 100),
            patch.object(materializer, "BATCH_SIZE", 1),
        ):
            mock_s3 = MagicMock()
            writer = materializer._ChunkWriter(s3=mock_s3)

            writer.append(b"line-0\n")
            writer.abort()

            assert mock_s3.upload_file.call_args_list == []
