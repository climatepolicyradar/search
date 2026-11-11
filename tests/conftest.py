"""Pytest configuration and shared fixtures."""

import os
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager

import boto3
import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import find
from hypothesis import strategies as st
from moto import mock_aws

from api.main import create_app
from api.state import State
from api.utils import documents_engine
from relevance_tests import TestResult
from search import Primitive
from search.identifiers import generate_id
from search.testcase import RecallTestCase
from tests.common_strategies import (
    document_strategy,
    label_strategy,
    passage_strategy,
)
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)
from tests.http import MockHandler


def override_dependency[T](
    app: FastAPI,
    key: Callable[..., object],
    value: T,
) -> Generator[T]:
    app.dependency_overrides[key] = lambda: value
    try:
        yield value
    finally:
        del app.dependency_overrides[key]


@pytest.fixture(scope="function")
def handler() -> MockHandler:
    return MockHandler()

@pytest.fixture(scope="function")
async def http_client(handler: MockHandler) -> AsyncGenerator[httpx2.AsyncClient, None]:
    transport = httpx2.MockTransport(handler=handler.handle)
    async with httpx2.AsyncClient(transport=transport) as client:
        yield client

@pytest.fixture(scope="function")
async def live_http_client() -> AsyncGenerator[httpx2.AsyncClient, None]:
    """A real (unmocked) client, for tests that hit a live Vespa instance."""
    async with httpx2.AsyncClient() as client:
        yield client

@pytest.fixture(scope="function")
def app(http_client: httpx2.AsyncClient) -> FastAPI:
    """
    An app of its own, with Vespa wired to `http_client` instead of the network.

    `api.main.app` is built once at import and its `app.state` lives for the
    whole process, so a client left there by one test's lifespan is still there
    - closed - for the next. Building one per test keeps that state per test.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.deps = State(httpx=http_client)
        yield

    return create_app(lifespan=lifespan)


@pytest.fixture(scope="function")
def test_client(app: FastAPI) -> Generator[TestClient, None]:
    """
    A client that has entered the app's lifespan.

    The lifespan runs before any request, so `dependency_overrides` cannot
    reach what it builds. Entering it here makes that the default, rather than
    something each test has to remember.
    """
    with TestClient(app=app, base_url="http://localhost") as client:
        yield client


@pytest.fixture(scope="function")
def stub_engine(app: FastAPI) -> Generator[StubDocumentSearchEngine]:
    yield from override_dependency(
        app=app,
        key=documents_engine,
        value=StubDocumentSearchEngine(),
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
        _test_data_cache["labels"] = _generate_items(label_strategy, n_test_items)
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
    engine_id = generate_id("JSONLabelSearchEngine")

    return TestResult(
        test_case=simple_test_case,
        status="passed",
        search_engine_id=engine_id,
        search_results=test_labels[:3],  # Use first 3 labels
    )
