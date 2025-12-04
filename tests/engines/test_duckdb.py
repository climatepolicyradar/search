"""Tests specific to DuckDB implementation."""

import duckdb
import pytest

from search import Primitive
from search.document import Document
from search.engines.duckdb import (
    DuckDBDocumentSearchEngine,
    DuckDBSearchEngine,
    DuckDBTableSchema,
)
from search.label import Label
from search.passage import Passage


def test_whether_schema_round_trips_correctly(
    duckdb_schema: DuckDBTableSchema,
    test_documents: list[Document],
    test_passages: list[Passage],
    test_labels: list[Label],
):
    items: list[Primitive] = []
    if duckdb_schema.model_class == Document:
        items = test_documents
    elif duckdb_schema.model_class == Passage:
        items = test_passages
    elif duckdb_schema.model_class == Label:
        items = test_labels
    else:
        pytest.fail("Unknown model class")

    for item in items:
        row = duckdb_schema.extract_row(item)
        rebuilt_item = duckdb_schema.build_model(row)
        assert rebuilt_item == item


def test_whether_engine_initialization_inserts_correct_number_of_items(test_documents):
    engine = DuckDBDocumentSearchEngine(items=test_documents)
    rows = engine.conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert rows[0] == len(test_documents)


def test_whether_engine_initialization_handles_empty_list_of_input_items():
    engine = DuckDBDocumentSearchEngine(items=[])
    rows = engine.conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert rows[0] == 0


def test_whether_engine_initialization_handles_batching(generate_documents):
    documents = generate_documents(15)
    engine = DuckDBDocumentSearchEngine(items=documents, batch_size=5)
    rows = engine.conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert rows[0] == len(documents)


@pytest.mark.parametrize(
    "injection_attempt",
    [
        "'; DROP TABLE documents; --",
        "' OR '1'='1",
        "'; SELECT * FROM documents; --",
        "test'term",
        "test'; DELETE FROM documents WHERE '1'='1",
    ],
)
def test_whether_search_is_safe_from_sql_injection(
    any_duckdb_engine: DuckDBSearchEngine, injection_attempt: str
):
    results = any_duckdb_engine.search(injection_attempt)
    assert isinstance(results, list)

    # Verify table still exists and is queryable
    all_results = any_duckdb_engine.search("")
    assert isinstance(all_results, list)


def test_whether_engine_can_initialize_from_db_path(
    tmp_path,
    any_duckdb_engine: DuckDBSearchEngine,
    test_documents: list[Document],
    test_passages: list[Passage],
    test_labels: list[Label],
):
    """
    Verify that an engine can be initialised from a DuckDB database file

    We do this by creating a new connection to the target file, and copying the table
    structure and data from our test database into it. We then initialise a new engine
    from that file to verify that it loads, and performs a search.
    """
    db_path = tmp_path / "test.duckdb"

    # Create a new connection to the target file and copy the table structure and data
    file_conn = duckdb.connect(str(db_path))
    file_conn.execute(any_duckdb_engine.schema.create_sql)

    # Copy all data from the in-memory connection to the file connection
    # We need to read from the source connection and insert into the target
    table_name = any_duckdb_engine.schema.table_name
    rows = any_duckdb_engine.conn.execute(f"SELECT * FROM {table_name}").fetchall()

    # Get column names for the INSERT statement
    columns = any_duckdb_engine.conn.execute(f"DESCRIBE {table_name}").fetchall()
    column_names = [col[0] for col in columns]
    columns_str = ", ".join(column_names)
    placeholders = ", ".join(["?" for _ in column_names])

    insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
    file_conn.executemany(insert_sql, rows)
    file_conn.close()

    # Now initialize a new engine from the file
    engine_class = any_duckdb_engine.__class__
    new_engine = engine_class(db_path=db_path)

    # get a valid search term from the test documents
    search_term: str = ""
    if any_duckdb_engine.schema.model_class == Document:
        search_term = test_documents[0].title
    elif any_duckdb_engine.schema.model_class == Passage:
        search_term = test_passages[0].text
    elif any_duckdb_engine.schema.model_class == Label:
        search_term = test_labels[0].preferred_label
    else:
        pytest.fail("Unknown model class")

    results = new_engine.search(search_term)
    assert len(results) >= 1
