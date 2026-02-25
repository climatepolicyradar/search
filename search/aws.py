"""AWS utility functions for interacting with S3 and SSM."""

from pathlib import Path

import boto3
from botocore.client import BaseClient

from search.config import AWS_PROFILE, AWS_REGION, BUCKET_NAME, DATA_DIR
from search.log import get_logger

logger = get_logger(__name__)


def get_aws_session() -> boto3.Session:
    """
    Get a boto3 session configured with the AWS profile and region from config.

    In local development, uses the AWS_PROFILE
    In containerized environments (ECS), uses the task IAM role (profile_name=None).
    """
    return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)


def get_s3_client() -> BaseClient:
    """Get an S3 client using the configured session."""
    session = get_aws_session()
    return session.client("s3")


def get_ssm_client() -> BaseClient:
    """Get an SSM client using the configured session."""
    session = get_aws_session()
    return session.client("ssm")


def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    """
    Get a parameter from AWS Systems Manager Parameter Store.

    Args:
        name: The name of the parameter to retrieve
        with_decryption: Whether to decrypt SecureString parameters (default: True)

    Returns:
        The parameter value as a string
    """
    ssm = get_ssm_client()
    response = ssm.get_parameter(Name=name, WithDecryption=with_decryption)
    return response["Parameter"]["Value"]


def upload_file_to_s3(
    file_path: Path, bucket_name: str | None = None, s3_key: str | None = None
) -> None:
    """
    Upload a file to S3.

    Args:
        file_path: Path to the local file to upload
        bucket_name: S3 bucket name (defaults to BUCKET_NAME env var if not provided)
        s3_key: S3 key/object name (defaults to file_path.name if not provided)
    """
    s3 = get_s3_client()
    if bucket_name is None:
        bucket_name = BUCKET_NAME
    if s3_key is None:
        s3_key = file_path.name

    s3.upload_file(str(file_path), bucket_name, s3_key)
    logger.info(f"Uploaded '{file_path}' to 's3://{bucket_name}/{s3_key}'")


def download_file_from_s3(
    bucket_name: str,
    s3_key: str,
    local_path: Path | None = None,
    skip_if_present: bool = True,
) -> None:
    """
    Download a file from S3.

    Args:
        bucket_name: S3 bucket name
        s3_key: S3 key/object name (e.g. 'data/documents.jsonl')
        local_path: Path to the local file to download.
            If None, mirrors the S3 key structure under DATA_DIR
        skip_if_present: Skip download if file already exists in local path
    """
    if local_path is None:
        local_path = DATA_DIR / s3_key

    if local_path.exists() and skip_if_present:
        logger.info(
            f"Skipping download of '{s3_key}' from '{bucket_name}' as it already exists in the target location."
        )
        return

    # Create parent directories if needed
    local_path.parent.mkdir(parents=True, exist_ok=True)

    s3 = get_s3_client()
    try:
        s3.download_file(bucket_name, s3_key, str(local_path))
    except Exception as e:
        raise RuntimeError(
            f"Failed to download '{s3_key}' from 's3://{bucket_name}'"
        ) from e
