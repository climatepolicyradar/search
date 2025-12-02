"""Pytest configuration and shared fixtures."""

import os

import boto3
import pytest
from hypothesis import find
from hypothesis import strategies as st
from moto import mock_aws

from search import Primitive
from tests.common_strategies import document_strategy, label_strategy, passage_strategy


@pytest.fixture(scope="function")
def mock_aws_creds():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_SECURITY_TOKEN"] = "test"
    os.environ["AWS_SESSION_TOKEN"] = "test"


@pytest.fixture
def s3_client(mock_aws_creds):
    """Fixture providing a mocked S3 client using moto."""
    with mock_aws():
        yield boto3.client("s3", region_name="eu-west-1")


@pytest.fixture
def ssm_client(mock_aws_creds):
    """Fixture providing a mocked SSM client using moto."""
    with mock_aws():
        yield boto3.client("ssm", region_name="eu-west-1")


_test_data_cache = {}


@pytest.fixture(scope="session")
def _generate_test_data() -> dict[str, list[Primitive]]:
    """Generate test data once per test session"""

    n_test_items = 7

    if "documents" not in _test_data_cache:
        _test_data_cache["documents"] = find(
            st.lists(document_strategy(), min_size=n_test_items, max_size=n_test_items),
            lambda _: True,
        )
    if "passages" not in _test_data_cache:
        _test_data_cache["passages"] = find(
            st.lists(passage_strategy(), min_size=n_test_items, max_size=n_test_items),
            lambda _: True,
        )
    if "labels" not in _test_data_cache:
        _test_data_cache["labels"] = find(
            st.lists(label_strategy(), min_size=n_test_items, max_size=n_test_items),
            lambda _: True,
        )
    return _test_data_cache


@pytest.fixture
def test_documents(_generate_test_data):
    """Generate a list of Document objects for testing using strategies."""
    return _test_data_cache["documents"]


@pytest.fixture
def test_passages(_generate_test_data):
    """Generate a list of Passage objects for testing using strategies."""
    return _test_data_cache["passages"]


@pytest.fixture
def test_labels(_generate_test_data):
    """Generate a list of Label objects for testing using strategies."""
    return _test_data_cache["labels"]
