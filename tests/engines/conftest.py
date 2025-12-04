"""Shared fixtures for engine tests."""

import pytest

from search import Primitive
from search.document import Document
from search.engines import SearchEngine
from search.engines.duckdb import (
    DuckDBDocumentSearchEngine,
    DuckDBDocumentTableSchema,
    DuckDBLabelSearchEngine,
    DuckDBLabelTableSchema,
    DuckDBPassageSearchEngine,
    DuckDBPassageTableSchema,
    DuckDBSearchEngine,
    DuckDBTableSchema,
)
from search.engines.json import (
    JSONDocumentSearchEngine,
    JSONDocumentSearchSchema,
    JSONLabelSearchEngine,
    JSONLabelSearchSchema,
    JSONPassageSearchEngine,
    JSONPassageSearchSchema,
    JSONSearchSchema,
)
from search.label import Label
from search.passage import Passage


# JSON schema fixtures
@pytest.fixture
def json_document_search_schema():
    return JSONDocumentSearchSchema()


@pytest.fixture
def json_passage_search_schema():
    return JSONPassageSearchSchema()


@pytest.fixture
def json_label_search_schema():
    return JSONLabelSearchSchema()


# JSON engine fixtures
@pytest.fixture
def json_document_engine(test_documents):
    return JSONDocumentSearchEngine(items=test_documents)


@pytest.fixture
def json_passage_engine(test_passages):
    return JSONPassageSearchEngine(items=test_passages)


@pytest.fixture
def json_label_engine(test_labels):
    return JSONLabelSearchEngine(items=test_labels)


# DuckDB schema fixtures
@pytest.fixture
def duckdb_document_schema():
    return DuckDBDocumentTableSchema()


@pytest.fixture
def duckdb_passage_schema():
    return DuckDBPassageTableSchema()


@pytest.fixture
def duckdb_label_schema():
    return DuckDBLabelTableSchema()


# DuckDB engine fixtures
@pytest.fixture
def duckdb_document_engine(test_documents):
    return DuckDBDocumentSearchEngine(items=test_documents)


@pytest.fixture
def duckdb_passage_engine(test_passages):
    return DuckDBPassageSearchEngine(items=test_passages)


@pytest.fixture
def duckdb_label_engine(test_labels):
    return DuckDBLabelSearchEngine(items=test_labels)


# Parametrized fixtures for all schemas and engines
@pytest.fixture(
    params=[
        "duckdb_document_schema",
        "duckdb_passage_schema",
        "duckdb_label_schema",
    ]
)
def duckdb_schema(request) -> DuckDBTableSchema:
    """Provides a DuckDB table schema."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_document_search_schema",
        "json_passage_search_schema",
        "json_label_search_schema",
    ]
)
def search_schema(request) -> JSONSearchSchema:
    """Provides a JSON search schema."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_document_engine",
        "duckdb_document_engine",
    ]
)
def document_engine(request) -> SearchEngine[Document]:
    """Provides both JSON and DuckDB document engines."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_passage_engine",
        "duckdb_passage_engine",
    ]
)
def passage_engine(request) -> SearchEngine[Passage]:
    """Provides both JSON and DuckDB passage engines."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_label_engine",
        "duckdb_label_engine",
    ]
)
def label_engine(request) -> SearchEngine[Label]:
    """Provides both JSON and DuckDB label engines."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_document_engine",
        "json_passage_engine",
        "json_label_engine",
    ]
)
def any_json_engine(request) -> SearchEngine:
    """Provides a JSON search engine."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "duckdb_document_engine",
        "duckdb_passage_engine",
        "duckdb_label_engine",
    ]
)
def any_duckdb_engine(request) -> DuckDBSearchEngine:
    """Provides a DuckDB search engine."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_document_engine",
        "duckdb_document_engine",
        "json_passage_engine",
        "duckdb_passage_engine",
        "json_label_engine",
        "duckdb_label_engine",
    ]
)
def any_engine(request) -> SearchEngine:
    """Provides all engine types."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "test_documents",
        "test_passages",
        "test_labels",
    ]
)
def test_items(request) -> list[Primitive]:
    """Provides test items for all engine types."""
    return request.getfixturevalue(request.param)
