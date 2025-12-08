"""Pytest configuration and shared fixtures."""

import os

import boto3
import pytest
from hypothesis import find
from hypothesis import strategies as st
from moto import mock_aws

from search import Primitive
from search.label import Label
from tests.common_strategies import (
    document_strategy,
    label_data_strategy,
    label_strategy,
    passage_strategy,
)


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


def _generate_items(strategy, count: int) -> list[Primitive]:
    """Generate a specific number of items using a Hypothesis strategy."""
    return find(
        st.lists(strategy(), min_size=count, max_size=count),
        lambda _: True,
    )


@pytest.fixture(scope="session")
def _generate_test_data() -> dict[str, list[Primitive]]:
    """Generate default test data once per test session (7 items each)."""

    n_test_items = 7

    if "documents" not in _test_data_cache:
        _test_data_cache["documents"] = _generate_items(document_strategy, n_test_items)
    if "passages" not in _test_data_cache:
        _test_data_cache["passages"] = _generate_items(passage_strategy, n_test_items)
    if "labels" not in _test_data_cache:
        # Generate labels, ensuring at least one has alternative_labels and description
        labels = _generate_items(label_strategy, n_test_items)
        # Ensure at least one label has alternative_labels
        if not any(label.alternative_labels for label in labels):
            label_with_alts = Label(
                **find(
                    label_data_strategy(),
                    lambda data: len(data.get("alternative_labels", [])) > 0,
                )
            )
            labels[0] = label_with_alts
        # Ensure at least one label has description
        if not any(label.description for label in labels):
            label_with_desc = Label(
                **find(
                    label_data_strategy(),
                    lambda data: data.get("description") is not None,
                )
            )
            # Replace the last label if first one was already replaced
            labels[-1] = label_with_desc
        _test_data_cache["labels"] = labels
    return _test_data_cache


@pytest.fixture
def test_documents(_generate_test_data):
    """Generate a list of Document objects for testing using strategies (default: 7 items)."""
    return _test_data_cache["documents"]


@pytest.fixture
def test_passages(_generate_test_data):
    """Generate a list of Passage objects for testing using strategies (default: 7 items)."""
    return _test_data_cache["passages"]


@pytest.fixture
def test_labels(_generate_test_data):
    """Generate a list of Label objects for testing using strategies (default: 7 items)."""
    return _test_data_cache["labels"]


# Parametrizable fixtures for generating specific numbers of items
@pytest.fixture
def generate_documents():
    """
    Factory fixture to generate a specific number of documents.

    Usage:
        def test_something(generate_documents):
            docs = generate_documents(100)  # Generate 100 documents
    """

    def _generate(count: int):
        return _generate_items(document_strategy, count)

    return _generate


@pytest.fixture
def generate_passages():
    """
    Factory fixture to generate a specific number of passages.

    Usage:
        def test_something(generate_passages):
            passages = generate_passages(100)  # Generate 100 passages
    """

    def _generate(count: int):
        return _generate_items(passage_strategy, count)

    return _generate


@pytest.fixture
def generate_labels():
    """
    Factory fixture to generate a specific number of labels.

    Usage:
        def test_something(generate_labels):
            labels = generate_labels(100)  # Generate 100 labels
    """

    def _generate(count: int):
        return _generate_items(label_strategy, count)

    return _generate
