"""Pytest configuration and shared fixtures."""

import os

import boto3
import pytest
from hypothesis import find
from hypothesis import strategies as st
from moto import mock_aws

from search import Primitive
from tests.common_strategies import (
    document_strategy,
    label_strategy,
    passage_strategy,
)


@pytest.fixture(scope="function")
def mock_aws_creds():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"  # nosec B105
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"  # nosec B105
    os.environ["AWS_SECURITY_TOKEN"] = "test"  # nosec B105
    os.environ["AWS_SESSION_TOKEN"] = "test"  # nosec B105


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


def _generate_items(strategy, count: int) -> list[Primitive]:
    """Generate a specific number of items using a Hypothesis strategy."""
    return find(
        st.lists(strategy(), min_size=count, max_size=count),
        lambda _: True,
    )


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

