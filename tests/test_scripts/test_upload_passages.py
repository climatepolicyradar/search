"""Tests for upload_passages.py script."""

import json
from unittest.mock import patch

import duckdb
from hypothesis import find
from hypothesis import strategies as st
from prefect.testing.utilities import prefect_test_harness

from search.passage import Passage
from tests.common_strategies import huggingface_row_strategy


def test_whether_upload_passages_creates_files(
    tmp_path, create_mock_huggingface_dataset
):
    """
    Verify upload_passages creates both JSONL and DuckDB files.

    This test verifies:
    - Both output files are created
    - Files contain the correct number of passages
    - JSONL file contains valid Passage JSON
    - DuckDB file contains queryable data
    - upload_file_to_s3 is called for both files
    """
    rows = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=True,
                include_text_block=True,
                include_text_block_id=True,
                include_document_id=True,
            ),
            min_size=20,
            max_size=20,
        ),
        lambda _: True,
    )

    mock_dataset = create_mock_huggingface_dataset(rows)
    passages_path_stem = tmp_path / "passages"
    jsonl_path = passages_path_stem.with_suffix(".jsonl")
    duckdb_path = passages_path_stem.with_suffix(".duckdb")

    mock_dataset_dir = tmp_path / "datasets" / "mock"
    mock_parquet_path = mock_dataset_dir / "data.parquet"

    mock_dataset_dir.mkdir(parents=True, exist_ok=True)
    mock_dataset.to_parquet(str(mock_parquet_path))

    with prefect_test_harness():
        with (
            patch("scripts.data_uploaders.upload_passages.snapshot_download"),
            patch(
                "scripts.data_uploaders.upload_passages.HF_CACHE_DIR",
                tmp_path,
            ),
            patch(
                "scripts.data_uploaders.upload_passages.DATASET_NAME",
                "mock",
            ),
            patch(
                "scripts.data_uploaders.upload_passages.PASSAGES_PATH_STEM",
                passages_path_stem,
            ),
            patch(
                "scripts.data_uploaders.upload_passages.upload_file_to_s3"
            ) as mock_upload,
        ):
            from scripts.data_uploaders.upload_passages import upload_passages_databases

            upload_passages_databases()

            # Verify JSONL file
            assert jsonl_path.exists(), "JSONL file should be created"
            with open(jsonl_path) as f:
                lines = [line for line in f if line.strip()]

            assert len(lines) == 20, "JSONL should contain 20 passages"

            # Verify first line is valid Passage JSON
            first_passage = Passage.model_validate_json(lines[0])
            assert first_passage.id is not None

            # Verify DuckDB file
            assert duckdb_path.exists(), "DuckDB file should be created"
            conn = duckdb.connect(str(duckdb_path), read_only=True)
            count = conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
            conn.close()
            assert count == 20, "DuckDB and JSONL should have same count"

            # Verify uploads
            assert mock_upload.call_count == 2, "Should upload both files"
            uploaded_paths = [call[0][0] for call in mock_upload.call_args_list]
            assert jsonl_path in uploaded_paths
            assert duckdb_path in uploaded_paths


def test_whether_upload_passages_filters_rows_missing_required_fields(
    tmp_path, create_mock_huggingface_dataset
):
    """Verify rows missing source_url or text are filtered out."""
    # 5 rows with all required fields
    rows_valid = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=True,
                include_text_block=True,
                include_document_id=True,
            ),
            min_size=5,
            max_size=5,
        ),
        lambda _: True,
    )

    # 3 rows missing source_url
    rows_no_url = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=False,
                include_text_block=True,
                include_document_id=True,
            ),
            min_size=3,
            max_size=3,
        ),
        lambda _: True,
    )

    # 3 rows missing text_block.text
    rows_no_text = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=True,
                include_text_block=False,
                include_document_id=True,
            ),
            min_size=3,
            max_size=3,
        ),
        lambda _: True,
    )

    all_rows = rows_valid + rows_no_url + rows_no_text  # 11 rows, only 5 valid
    mock_dataset = create_mock_huggingface_dataset(all_rows)
    passages_path_stem = tmp_path / "passages"
    jsonl_path = passages_path_stem.with_suffix(".jsonl")

    mock_dataset_dir = tmp_path / "datasets" / "mock"
    mock_parquet_path = mock_dataset_dir / "data.parquet"

    mock_dataset_dir.mkdir(parents=True, exist_ok=True)
    mock_dataset.to_parquet(str(mock_parquet_path))

    with prefect_test_harness():
        with (
            patch("scripts.data_uploaders.upload_passages.snapshot_download"),
            patch(
                "scripts.data_uploaders.upload_passages.HF_CACHE_DIR",
                tmp_path,
            ),
            patch(
                "scripts.data_uploaders.upload_passages.DATASET_NAME",
                "mock",
            ),
            patch(
                "scripts.data_uploaders.upload_passages.PASSAGES_PATH_STEM",
                passages_path_stem,
            ),
            patch("scripts.data_uploaders.upload_passages.upload_file_to_s3"),
        ):
            from scripts.data_uploaders.upload_passages import upload_passages_databases

            upload_passages_databases()

            with open(jsonl_path) as f:
                passage_count = sum(1 for line in f if line.strip())
                created_passages = [json.loads(line) for line in f]

            assert (
                passage_count == 5
            ), "Should only create passages for rows with source_url and text"
            assert all(
                [passage["source_url"] is not None for passage in created_passages]
            ), "All created passages should have a source_url"
            assert all(
                [passage["text"] is not None for passage in created_passages]
            ), "All created passages should have text"
