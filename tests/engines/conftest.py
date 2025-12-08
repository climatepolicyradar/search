"""Shared fixtures for engine tests."""

import pytest

from search import Primitive
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


# Individual schema fixtures
@pytest.fixture
def json_document_search_schema():
    return JSONDocumentSearchSchema()


@pytest.fixture
def json_passage_search_schema():
    return JSONPassageSearchSchema()


@pytest.fixture
def json_label_search_schema():
    return JSONLabelSearchSchema()


@pytest.fixture
def duckdb_document_schema():
    return DuckDBDocumentTableSchema()


@pytest.fixture
def duckdb_passage_schema():
    return DuckDBPassageTableSchema()


@pytest.fixture
def duckdb_label_schema():
    return DuckDBLabelTableSchema()


# Parametrized schema fixtures
@pytest.fixture(
    params=[
        "duckdb_document_schema",
        "duckdb_passage_schema",
        "duckdb_label_schema",
    ]
)
def duckdb_schema(request) -> DuckDBTableSchema:
    """Provides any DuckDB table schema."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "json_document_search_schema",
        "json_passage_search_schema",
        "json_label_search_schema",
    ]
)
def json_schema(request) -> JSONSearchSchema:
    """Provides any JSON search schema."""
    return request.getfixturevalue(request.param)


# Helper fixtures for building engines
@pytest.fixture
def _json_document_engine(test_documents):
    return JSONDocumentSearchEngine(items=test_documents)


@pytest.fixture
def _json_passage_engine(test_passages):
    return JSONPassageSearchEngine(items=test_passages)


@pytest.fixture
def _json_label_engine(test_labels):
    return JSONLabelSearchEngine(items=test_labels)


@pytest.fixture
def _duckdb_document_engine(test_documents):
    return DuckDBDocumentSearchEngine(items=test_documents)


@pytest.fixture
def _duckdb_passage_engine(test_passages):
    return DuckDBPassageSearchEngine(items=test_passages)


@pytest.fixture
def _duckdb_label_engine(test_labels):
    return DuckDBLabelSearchEngine(items=test_labels)


# Parametrized engine fixtures
@pytest.fixture(
    params=[
        "_json_document_engine",
        "_json_passage_engine",
        "_json_label_engine",
    ]
)
def any_json_engine(request) -> SearchEngine:
    """Provides any JSON search engine."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "_duckdb_document_engine",
        "_duckdb_passage_engine",
        "_duckdb_label_engine",
    ]
)
def any_duckdb_engine(request) -> DuckDBSearchEngine:
    """Provides any DuckDB search engine."""
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "_json_document_engine",
        "_duckdb_document_engine",
        "_json_passage_engine",
        "_duckdb_passage_engine",
        "_json_label_engine",
        "_duckdb_label_engine",
    ]
)
def any_engine(request) -> SearchEngine:
    """Provides any engine type."""
    return request.getfixturevalue(request.param)


# Parametrised item fixture
@pytest.fixture(
    params=[
        "test_documents",
        "test_passages",
        "test_labels",
    ]
)
def any_items(request) -> list[Primitive]:
    """Provides any test items."""
    return request.getfixturevalue(request.param)


# Paired engine + items fixtures
@pytest.fixture(
    params=[
        ("_json_document_engine", "test_documents"),
        ("_json_passage_engine", "test_passages"),
        ("_json_label_engine", "test_labels"),
        ("_duckdb_document_engine", "test_documents"),
        ("_duckdb_passage_engine", "test_passages"),
        ("_duckdb_label_engine", "test_labels"),
    ],
    ids=[
        "json_document",
        "json_passage",
        "json_label",
        "duckdb_document",
        "duckdb_passage",
        "duckdb_label",
    ],
)
def any_engine_and_items(request) -> tuple[SearchEngine, list[Primitive]]:
    """
    Provides any engine paired with its matching test items.

    This is the preferred fixture for most engine tests.
    """
    engine_name, items_name = request.param
    engine = request.getfixturevalue(engine_name)
    items = request.getfixturevalue(items_name)
    return engine, items


@pytest.fixture(
    params=[
        ("_duckdb_document_engine", "test_documents"),
        ("_duckdb_passage_engine", "test_passages"),
        ("_duckdb_label_engine", "test_labels"),
    ],
    ids=["duckdb_document", "duckdb_passage", "duckdb_label"],
)
def any_duckdb_engine_and_items(request) -> tuple[DuckDBSearchEngine, list[Primitive]]:
    """Provides any DuckDB engine paired with its matching test items."""
    engine_name, items_name = request.param
    engine = request.getfixturevalue(engine_name)
    items = request.getfixturevalue(items_name)
    return engine, items


@pytest.fixture(
    params=[
        ("_json_document_engine", "test_documents"),
        ("_json_passage_engine", "test_passages"),
        ("_json_label_engine", "test_labels"),
    ],
    ids=["json_document", "json_passage", "json_label"],
)
def any_json_engine_and_items(request) -> tuple[SearchEngine, list[Primitive]]:
    """Provides any JSON engine paired with its matching test items."""
    engine_name, items_name = request.param
    engine = request.getfixturevalue(engine_name)
    items = request.getfixturevalue(items_name)
    return engine, items


@pytest.fixture(
    params=[
        ("duckdb_document_schema", "test_documents"),
        ("duckdb_passage_schema", "test_passages"),
        ("duckdb_label_schema", "test_labels"),
    ],
    ids=["duckdb_document", "duckdb_passage", "duckdb_label"],
)
def duckdb_schema_and_items(request) -> tuple[DuckDBTableSchema, list[Primitive]]:
    """Provides any DuckDB schema paired with its matching test items."""
    schema_name, items_name = request.param
    schema = request.getfixturevalue(schema_name)
    items = request.getfixturevalue(items_name)
    return schema, items


@pytest.fixture(
    params=[
        ("json_document_search_schema", "test_documents"),
        ("json_passage_search_schema", "test_passages"),
        ("json_label_search_schema", "test_labels"),
    ],
    ids=["json_document", "json_passage", "json_label"],
)
def json_schema_and_items(request) -> tuple[JSONSearchSchema, list[Primitive]]:
    """Provides any JSON schema paired with its matching test items."""
    schema_name, items_name = request.param
    schema = request.getfixturevalue(schema_name)
    items = request.getfixturevalue(items_name)
    return schema, items
