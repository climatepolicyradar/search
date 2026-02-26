"""Tests for AWS utility functions."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from search.aws import (
    download_file_from_s3,
    get_aws_session,
    get_ssm_parameter,
    upload_file_to_s3,
)


@pytest.mark.parametrize(
    "profile,region",
    [
        (None, "eu-west-1"),
        ("production", "eu-west-1"),
        ("production", "us-east-1"),
    ],
)
def test_whether_get_aws_session_creates_session_with_correct_profile_and_region(
    profile, region
):
    with (
        patch("boto3.Session") as mock_session_class,
        patch("search.aws.AWS_PROFILE", profile),
        patch("search.aws.AWS_REGION", region),
    ):
        get_aws_session()

        # Verify boto3.Session was called with correct parameters from our config
        mock_session_class.assert_called_once_with(
            profile_name=profile, region_name=region
        )


@pytest.mark.parametrize(
    "with_decryption",
    [True, False],
)
def test_whether_the_decryption_parameter_is_passed_to_the_ssm_client(with_decryption):
    with patch("search.aws.get_ssm_client") as mock_get_client:
        mock_client_instance = mock_get_client.return_value
        mock_client_instance.get_parameter.return_value = {
            "Parameter": {"Value": "test-value"}
        }

        result = get_ssm_parameter("test-param", with_decryption=with_decryption)

        mock_get_client.assert_called_once()
        mock_client_instance.get_parameter.assert_called_once_with(
            Name="test-param", WithDecryption=with_decryption
        )
        assert result == "test-value"


def test_whether_default_decryption_value_is_used_when_left_unspecified():
    with patch("search.aws.get_ssm_client") as mock_get_client:
        mock_client_instance = mock_get_client.return_value
        mock_client_instance.get_parameter.return_value = {
            "Parameter": {"Value": "test-value"}
        }

        get_ssm_parameter("test-param")

        mock_client_instance.get_parameter.assert_called_once_with(
            Name="test-param", WithDecryption=True
        )


@pytest.mark.parametrize(
    "bucket_name,s3_key",
    [
        (None, None),  # Default: uses BUCKET_NAME and file_path.name
        ("custom-bucket", None),  # Custom bucket, default key
        (None, "custom/key.txt"),  # Default bucket, custom key
        ("custom-bucket", "custom/key.txt"),  # Both custom
    ],
)
def test_whether_upload_file_to_s3_resolves_bucket_and_key_correctly(
    bucket_name, s3_key
):
    """
    Verifies that upload_file_to_s3:

    - Calls get_s3_client() to get the S3 client
    - Uses BUCKET_NAME from config when bucket_name is None
    - Resolves s3_key (defaults to file_path.name when not provided)
    - Calls s3.upload_file() with the correct file path, bucket, and key
    - Logs an info message containing the bucket and key
    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
        tmp_file.write("test content")
        tmp_path = Path(tmp_file.name)

    try:
        # Determine expected values based on test parameters:
        # - If bucket_name is None, function will use BUCKET_NAME from config
        # - If s3_key is None, function will use file_path.name as the key
        default_bucket = "test-bucket"
        expected_bucket = bucket_name or default_bucket
        expected_key = s3_key or tmp_path.name

        with (
            patch("search.aws.get_s3_client") as mock_get_client,
            patch("search.aws.BUCKET_NAME", default_bucket),
            patch("search.aws.logger") as mock_logger,
        ):
            mock_s3_client = mock_get_client.return_value
            upload_file_to_s3(tmp_path, bucket_name=bucket_name, s3_key=s3_key)

            # Verify get_s3_client() was called to obtain the S3 client
            mock_get_client.assert_called_once()

            # Verify upload_file() was called with correct parameters:
            # file path (as string), bucket name (from BUCKET_NAME or custom), and S3 key
            mock_s3_client.upload_file.assert_called_once_with(
                str(tmp_path), expected_bucket, expected_key
            )

            # Verify an info log message was written containing bucket and key
            mock_logger.info.assert_called_once()
            assert expected_bucket in mock_logger.info.call_args[0][0]
            assert expected_key in mock_logger.info.call_args[0][0]
    finally:
        tmp_path.unlink()


@pytest.mark.parametrize(
    "local_path_suffix",
    [
        None,  # Default: uses DATA_DIR / s3_key
        "custom/file.jsonl",  # Custom path provided
    ],
    ids=["default_path", "custom_path"],
)
def test_whether_download_file_from_s3_constructs_local_path_correctly(
    local_path_suffix,
):
    """
    Verifies that download_file_from_s3:

    - Calls get_s3_client() to get the S3 client
    - Constructs the local path (default: DATA_DIR / s3_key, or uses provided custom path)
    - Calls s3.download_file() with the correct bucket, key, and local path
    - Creates parent directories for the download path
    """
    bucket_name = "test-bucket"
    s3_key = "data/documents.jsonl"

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        # Set up local_path and expected_path:
        # - If local_path_suffix is None, function uses DATA_DIR / s3_key
        # - If local_path_suffix is provided, function uses that path
        if local_path_suffix is None:
            local_path = None
            expected_path = data_dir / s3_key
        else:
            local_path = data_dir / local_path_suffix
            expected_path = local_path

        with (
            patch("search.aws.DATA_DIR", data_dir),
            patch("search.aws.get_s3_client") as mock_get_client,
        ):
            mock_s3_client = mock_get_client.return_value
            download_file_from_s3(bucket_name, s3_key, local_path)

            # Verify get_s3_client() was called to obtain the S3 client
            mock_get_client.assert_called_once()
            # Verify download_file() was called with correct parameters:
            # bucket_name, s3_key, and the constructed/provided local path
            mock_s3_client.download_file.assert_called_once_with(
                bucket_name, s3_key, str(expected_path)
            )

            # Verify parent directories were created (download_file_from_s3 calls
            # local_path.parent.mkdir(parents=True, exist_ok=True) before downloading)
            assert expected_path.parent.exists()


def test_whether_download_file_from_s3_raises_runtime_error_when_s3_download_fails():
    """
    Verifies that when s3.download_file() raises an exception, download_file_from_s3:

    - Catches the exception from the S3 client
    - Raises a RuntimeError with a descriptive message
    - Includes the s3_key and bucket_name in the error message for debugging
    """
    bucket_name = "test-bucket"
    s3_key = "data/documents.jsonl"

    with tempfile.TemporaryDirectory() as tmp_dir:
        data_dir = Path(tmp_dir) / "data"
        with (
            patch("search.aws.DATA_DIR", data_dir),
            patch("search.aws.get_s3_client") as mock_get_client,
        ):
            mock_s3_client = mock_get_client.return_value
            # Simulate an S3 error (e.g., bucket doesn't exist, access denied, etc.)
            mock_s3_client.download_file.side_effect = Exception("S3 error")

            # Verify that the function catches the S3 exception and raises
            # a RuntimeError with a message matching "Failed to download"
            with pytest.raises(RuntimeError, match="Failed to download"):
                download_file_from_s3(bucket_name, s3_key)
