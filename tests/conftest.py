"""Pytest configuration and shared fixtures."""

import os
from unittest.mock import patch

import boto3
import pytest
from hypothesis import find
from hypothesis import strategies as st
from knowledge_graph.identifiers import Identifier
from moto import mock_aws

from relevance_tests import TestResult
from search import Primitive
from search.label import Label
from search.testcase import RecallTestCase
from tests.common_strategies import (
    document_strategy,
    label_data_strategy,
    label_strategy,
    passage_strategy,
)


@pytest.fixture(scope="function", autouse=True)
def mock_prefect_decorators():
    """
    Mock Prefect decorators to prevent cloud authentication during tests.

    This fixture automatically mocks @flow and @task decorators to be identity
    functions, allowing decorated functions to execute as normal Python functions
    without attempting to connect to Prefect Cloud.
    """

    def identity_decorator(fn=None, **kwargs):
        """
        Identity decorator that handles both @decorator and @decorator() syntax.

        :param fn: Function to decorate (when used as @decorator)
        :param kwargs: Keyword arguments (when used as @decorator(**kwargs))
        :return: The function unchanged, or a decorator that returns it unchanged
        """
        if fn is not None:
            # Used as @decorator (function passed directly)
            return fn
        # Used as @decorator() or @decorator(arg=value)
        return lambda f: f

    with patch("prefect.flow", identity_decorator):
        with patch("prefect.task", identity_decorator):
            yield


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


@pytest.fixture
def simple_test_case():
    """
    Create a simple TestCase for testing.

    :return: A TestCase instance with basic search parameters
    :rtype: TestCase
    """
    return RecallTestCase(
        search_terms="climate change",
        expected_result_ids=["pdhcqueu"],
        description="Test case for climate change search",
    )


@pytest.fixture
def another_test_case():
    """
    Create a different TestCase for testing comparisons.

    :return: A TestCase instance with different parameters than simple_test_case
    :rtype: TestCase
    """
    return RecallTestCase(
        search_terms="flood risk",
        expected_result_ids=["abcdwxyz"],
        description="Test case for flood risk search",
    )


@pytest.fixture
def simple_test_result(simple_test_case, test_labels):
    """
    Create a simple TestResult for testing.

    Uses a fixed search engine ID and test labels for consistent test behavior.

    :param simple_test_case: A simple test case fixture
    :type simple_test_case: TestCase
    :param test_labels: List of test label objects
    :type test_labels: list[Label]
    :return: A TestResult instance
    :rtype: TestResult[Label]
    """
    # Create a deterministic engine ID for testing
    engine_id = Identifier.generate("JSONLabelSearchEngine")

    return TestResult(
        test_case=simple_test_case,
        passed=True,
        search_engine_id=engine_id,
        search_results=test_labels[:3],  # Use first 3 labels
    )
