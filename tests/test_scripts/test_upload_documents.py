"""Tests for upload_documents.py script."""

import json
from unittest.mock import patch

import duckdb
from hypothesis import find
from hypothesis import strategies as st

from search.document import Document
from tests.common_strategies import huggingface_row_strategy


def test_whether_upload_documents_creates_files(
    tmp_path, create_mock_huggingface_dataset
):
    """
    Verify upload_documents creates both JSONL and DuckDB files.

    This test verifies:
    - Both output files are created
    - Files contain the correct number of documents
    - JSONL file contains valid Document JSON
    - DuckDB file contains queryable data
    - upload_file_to_s3 is called for both files
    """

    rows = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=True,
                include_title=True,
                include_description=True,
                include_document_id=True,
            ),
            min_size=10,
            max_size=10,
        ),
        lambda _: True,
    )

    mock_dataset = create_mock_huggingface_dataset(rows)
    documents_path_stem = tmp_path / "documents"
    jsonl_path = documents_path_stem.with_suffix(".jsonl")
    duckdb_path = documents_path_stem.with_suffix(".duckdb")

    with (
        patch(
            "scripts.data_uploaders.upload_documents.load_dataset",
            return_value=mock_dataset,
        ),
        patch(
            "scripts.data_uploaders.upload_documents.DOCUMENTS_PATH_STEM",
            documents_path_stem,
        ),
        patch(
            "scripts.data_uploaders.upload_documents.upload_file_to_s3"
        ) as mock_upload,
    ):
        from scripts.data_uploaders.upload_documents import main

        main()

        # Verify JSONL file
        assert jsonl_path.exists(), "JSONL file should be created"
        with open(jsonl_path) as f:
            lines = [line for line in f if line.strip()]

        assert len(lines) > 0, "JSONL should contain documents"

        # Verify first line is valid Document JSON
        first_doc = Document.model_validate_json(lines[0])
        assert first_doc.id is not None

        # Verify DuckDB file
        assert duckdb_path.exists(), "DuckDB file should be created"
        conn = duckdb.connect(str(duckdb_path), read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
        assert count == len(lines), "DuckDB and JSONL should have same count"

        # Verify uploads
        assert mock_upload.call_count == 2, "Should upload both files"
        uploaded_paths = [call[0][0] for call in mock_upload.call_args_list]
        assert jsonl_path in uploaded_paths
        assert duckdb_path in uploaded_paths


def test_whether_upload_documents_filters_rows_without_source_url(
    tmp_path, create_mock_huggingface_dataset
):
    """Verify rows without source_url are filtered out."""

    rows_with_url = find(
        st.lists(
            huggingface_row_strategy(include_source_url=True, include_document_id=True),
            min_size=5,
            max_size=5,
        ),
        lambda rows: len(set(row["document_id"] for row in rows)) == 5,
    )

    rows_without_url = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=False, include_document_id=True
            ),
            min_size=5,
            max_size=5,
        ),
        lambda _: True,
    )

    all_rows = rows_with_url + rows_without_url
    mock_dataset = create_mock_huggingface_dataset(all_rows)
    documents_path_stem = tmp_path / "documents"
    jsonl_path = documents_path_stem.with_suffix(".jsonl")

    with (
        patch(
            "scripts.data_uploaders.upload_documents.load_dataset",
            return_value=mock_dataset,
        ),
        patch(
            "scripts.data_uploaders.upload_documents.DOCUMENTS_PATH_STEM",
            documents_path_stem,
        ),
        patch("scripts.data_uploaders.upload_documents.upload_file_to_s3"),
    ):
        from scripts.data_uploaders.upload_documents import main

        main()

        with open(jsonl_path) as f:
            doc_count = sum(1 for line in f if line.strip())
            created_documents = [json.loads(line) for line in f]

        assert doc_count == 5, "Should only create documents for rows with source_url"
        assert all([doc["source_url"] is not None for doc in created_documents])


def test_whether_upload_documents_returns_unique_document_ids(
    tmp_path, create_mock_huggingface_dataset
):
    """Verify duplicate document_ids result in single document."""

    base_row = find(
        huggingface_row_strategy(
            include_source_url=True,
            include_title=True,
            include_document_id=True,
        ),
        lambda _: True,
    )
    duplicate_rows = [base_row.copy(), base_row.copy(), base_row.copy()]

    unique_rows = find(
        st.lists(
            huggingface_row_strategy(
                include_source_url=True,
                include_title=True,
                include_document_id=True,
            ),
            min_size=2,
            max_size=2,
        ),
        lambda rows: all(row["document_id"] != base_row["document_id"] for row in rows),
    )

    all_rows = duplicate_rows + unique_rows  # 5 rows, 3 unique document_ids
    mock_dataset = create_mock_huggingface_dataset(all_rows)
    documents_path_stem = tmp_path / "documents"
    jsonl_path = documents_path_stem.with_suffix(".jsonl")

    with (
        patch(
            "scripts.data_uploaders.upload_documents.load_dataset",
            return_value=mock_dataset,
        ),
        patch(
            "scripts.data_uploaders.upload_documents.DOCUMENTS_PATH_STEM",
            documents_path_stem,
        ),
        patch("scripts.data_uploaders.upload_documents.upload_file_to_s3"),
    ):
        from scripts.data_uploaders.upload_documents import main

        main()

        with open(jsonl_path) as f:
            doc_count = sum(1 for line in f if line.strip())

        # Should only have 3 unique documents (1 from duplicates, 2 unique)
        assert doc_count == 3, "Should deduplicate by document_id"
