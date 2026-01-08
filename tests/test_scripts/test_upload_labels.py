"""Tests for upload_labels.py script."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import duckdb

from search.config import get_git_root
from search.label import Label

_project_root = get_git_root()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def test_whether_upload_labels_creates_files(
    tmp_path, ssm_with_wikibase_params, mock_wikibase_concepts
):
    """
    Verify upload_labels fetches SSM parameters and creates JSONL and DuckDB files.

    This test verifies:
    - Both JSONL and DuckDB files are created
    - Files contain the correct number of labels
    - upload_file_to_s3 is called for both files

    :param tmp_path: Pytest fixture providing temporary directory
    :type tmp_path: Path
    :param ssm_with_wikibase_params: SSM client with Wikibase credentials
    :type ssm_with_wikibase_params: boto3.client
    :param mock_wikibase_concepts: List of mock Wikibase concepts
    :type mock_wikibase_concepts: list[MagicMock]
    """
    labels_path_stem = tmp_path / "labels"
    jsonl_path = labels_path_stem.with_suffix(".jsonl")
    duckdb_path = labels_path_stem.with_suffix(".duckdb")

    mock_session = MagicMock()
    mock_session.get_concepts.return_value = mock_wikibase_concepts

    with (
        patch("search.aws.get_ssm_client", return_value=ssm_with_wikibase_params),
        patch(
            "scripts.data_uploaders.upload_labels.LABELS_PATH_STEM", labels_path_stem
        ),
        patch(
            "scripts.data_uploaders.upload_labels.WikibaseSession",
            return_value=mock_session,
        ),
        patch("scripts.data_uploaders.upload_labels.upload_file_to_s3") as mock_upload,
    ):
        upload_labels = importlib.import_module("scripts.data_uploaders.upload_labels")
        upload_labels.main()

        # Verify JSONL file exists and has correct number of lines
        assert jsonl_path.exists(), "JSONL file should be created"
        with open(jsonl_path) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == len(mock_wikibase_concepts), (
            f"JSONL should contain {len(mock_wikibase_concepts)} labels"
        )

        # Verify first line is valid Label JSON
        first_label = Label.model_validate_json(lines[0])
        assert first_label.id is not None

        # Verify DuckDB file exists and has correct count
        assert duckdb_path.exists(), "DuckDB file should be created"
        conn = duckdb.connect(str(duckdb_path), read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        conn.close()
        assert count == len(mock_wikibase_concepts), (
            "DuckDB should have same count as JSONL"
        )

        # Verify upload_file_to_s3 was called twice
        assert mock_upload.call_count == 2, "Should upload both JSONL and DuckDB files"
        uploaded_paths = [call[0][0] for call in mock_upload.call_args_list]
        assert jsonl_path in uploaded_paths, "JSONL path should be uploaded"
        assert duckdb_path in uploaded_paths, "DuckDB path should be uploaded"


def test_whether_upload_labels_creates_valid_labels_from_concepts(
    tmp_path, ssm_with_wikibase_params, mock_wikibase_concepts
):
    """Verify valid labels are created."""
    labels_path_stem = tmp_path / "labels"
    jsonl_path = labels_path_stem.with_suffix(".jsonl")

    mock_session = MagicMock()
    mock_session.get_concepts.return_value = mock_wikibase_concepts

    with (
        patch("search.aws.get_ssm_client", return_value=ssm_with_wikibase_params),
        patch(
            "scripts.data_uploaders.upload_labels.LABELS_PATH_STEM", labels_path_stem
        ),
        patch(
            "scripts.data_uploaders.upload_labels.WikibaseSession",
            return_value=mock_session,
        ),
        patch("scripts.data_uploaders.upload_labels.upload_file_to_s3"),
    ):
        from scripts.data_uploaders.upload_labels import main

        main()

        with open(jsonl_path) as f:
            labels = [Label.model_validate_json(line) for line in f if line.strip()]

        # Verify first label matches first concept
        first_concept = mock_wikibase_concepts[0]
        first_label = labels[0]

        assert first_label.preferred_label == first_concept.preferred_label
        assert first_label.alternative_labels == first_concept.alternative_labels
        assert first_label.negative_labels == first_concept.negative_labels
        assert first_label.description == first_concept.description
        assert first_label.source == "wikibase"
        assert first_label.id_at_source == str(first_concept.wikibase_id)
