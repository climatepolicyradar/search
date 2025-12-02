"""Tests for AWS utility functions."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import boto3
import pytest

from search.aws import (
    download_file_from_s3,
    get_aws_session,
    get_bucket_name,
    get_s3_client,
    get_ssm_client,
    get_ssm_parameter,
    upload_file_to_s3,
)


@pytest.mark.parametrize(
    "profile,region",
    [
        (None, "eu-west-1"),
        ("labs", "eu-west-1"),
        ("labs", "us-east-1"),
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
    "client_func,expected_service",
    [
        (get_s3_client, "s3"),
        (get_ssm_client, "ssm"),
    ],
)
@patch("search.aws.get_aws_session")
def test_whether_client_functions_call_get_aws_session_and_return_correct_client(
    mock_get_session, client_func, expected_service
):
    mock_session = boto3.Session(region_name="eu-west-1")
    mock_get_session.return_value = mock_session

    result = client_func()

    mock_get_session.assert_called_once()
    assert result is not None
    assert result.meta.service_model.service_name == expected_service


def test_whether_get_bucket_name_retrieves_bucket_name_from_environment_variable():
    with patch.dict(os.environ, {"BUCKET_NAME": "test-bucket"}, clear=True):
        result = get_bucket_name()
        assert result == "test-bucket"


def test_whether_get_bucket_name_raises_value_error_when_bucket_name_not_set():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="BUCKET_NAME is not set"):
            get_bucket_name()


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
    "bucket_name,s3_key,should_call_get_bucket_name",
    [
        (None, None, True),  # Default: uses get_bucket_name() and file_path.name
        ("custom-bucket", None, False),  # Custom bucket, default key
        (None, "custom/key.txt", True),  # Default bucket, custom key
        ("custom-bucket", "custom/key.txt", False),  # Both custom
    ],
)
def test_whether_upload_file_to_s3_resolves_bucket_and_key_correctly(
    bucket_name, s3_key, should_call_get_bucket_name
):
    """
    Verifies that upload_file_to_s3:

    - Calls get_s3_client() to get the S3 client
    - Calls get_bucket_name() when bucket_name is None (to get default from env var)
    - Resolves s3_key (defaults to file_path.name when not provided)
    - Calls s3.upload_file() with the correct file path, bucket, and key
    - Logs an info message containing the bucket and key
    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
        tmp_file.write("test content")
        tmp_path = Path(tmp_file.name)

    try:
        # Determine expected values based on test parameters:
        # - If bucket_name is None, function will call get_bucket_name() to get default
        # - If s3_key is None, function will use file_path.name as the key
        expected_bucket = bucket_name or "default-bucket"
        expected_key = s3_key or tmp_path.name

        with (
            patch("search.aws.get_s3_client") as mock_get_client,
            patch(
                "search.aws.get_bucket_name", return_value=expected_bucket
            ) as mock_get_bucket,
            patch("search.aws.logger") as mock_logger,
        ):
            mock_s3_client = mock_get_client.return_value
            upload_file_to_s3(tmp_path, bucket_name=bucket_name, s3_key=s3_key)

            # Verify get_s3_client() was called to obtain the S3 client
            mock_get_client.assert_called_once()
            # Verify get_bucket_name() is only called when bucket_name is None
            # (i.e., when we need to get the default bucket from environment)
            if should_call_get_bucket_name:
                mock_get_bucket.assert_called_once()
            else:
                mock_get_bucket.assert_not_called()

            # Verify upload_file() was called with correct parameters:
            # file path (as string), bucket name, and S3 key
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
