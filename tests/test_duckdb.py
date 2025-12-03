import duckdb
import pytest

from search.engines.duckdb import (
    create_documents_duckdb_table,
    create_labels_duckdb_table,
    create_passages_duckdb_table,
)


def test_whether_documents_table_has_correct_columns(tmp_path, test_documents):
    db_path = tmp_path / "test_documents.duckdb"
    create_documents_duckdb_table(db_path, test_documents)

    conn = duckdb.connect(str(db_path), read_only=True)
    columns = conn.execute("DESCRIBE documents").fetchall()
    conn.close()

    column_names = [col[0] for col in columns]
    expected_columns = [
        "id",
        "title",
        "source_url",
        "description",
        "original_document_id",
    ]
    assert set(column_names) == set(expected_columns)


def test_whether_documents_table_inserts_data_correctly(tmp_path, test_documents):
    db_path = tmp_path / "test_documents.duckdb"
    count = create_documents_duckdb_table(db_path, test_documents)

    assert count == len(test_documents)

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute("SELECT * FROM documents").fetchall()
    conn.close()

    assert len(rows) == len(test_documents)

    for i, doc in enumerate(test_documents):
        row = rows[i]
        assert row[0] == doc.id
        assert row[1] == doc.title
        assert row[2] == str(doc.source_url)
        assert row[3] == doc.description
        assert row[4] == doc.original_document_id


def test_whether_passages_table_has_correct_columns(tmp_path, test_passages):
    db_path = tmp_path / "test_passages.duckdb"
    create_passages_duckdb_table(db_path, test_passages)

    conn = duckdb.connect(str(db_path), read_only=True)
    columns = conn.execute("DESCRIBE passages").fetchall()
    conn.close()

    column_names = [col[0] for col in columns]
    expected_columns = ["id", "text", "document_id", "labels", "original_passage_id"]
    assert set(column_names) == set(expected_columns)


def test_whether_passages_table_inserts_data_correctly(tmp_path, test_passages):
    db_path = tmp_path / "test_passages.duckdb"
    count = create_passages_duckdb_table(db_path, test_passages)

    assert count == len(test_passages)

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute("SELECT * FROM passages").fetchall()
    conn.close()

    assert len(rows) == len(test_passages)

    for i, passage in enumerate(test_passages):
        row = rows[i]
        assert row[0] == passage.id
        assert row[1] == passage.text
        assert row[2] == passage.document_id
        assert row[3] == passage.labels
        assert row[4] == passage.original_passage_id


def test_whether_labels_table_has_correct_columns(tmp_path, test_labels):
    db_path = tmp_path / "test_labels.duckdb"
    create_labels_duckdb_table(db_path, test_labels)

    conn = duckdb.connect(str(db_path), read_only=True)
    columns = conn.execute("DESCRIBE labels").fetchall()
    conn.close()

    column_names = [col[0] for col in columns]
    expected_columns = [
        "id",
        "preferred_label",
        "alternative_labels",
        "negative_labels",
        "description",
    ]
    assert set(column_names) == set(expected_columns)


def test_whether_labels_table_inserts_data_correctly(tmp_path, test_labels):
    db_path = tmp_path / "test_labels.duckdb"
    count = create_labels_duckdb_table(db_path, test_labels)

    assert count == len(test_labels)

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute("SELECT * FROM labels").fetchall()
    conn.close()

    assert len(rows) == len(test_labels)

    for i, label in enumerate(test_labels):
        row = rows[i]
        assert row[0] == label.id
        assert row[1] == label.preferred_label
        assert row[2] == label.alternative_labels
        assert row[3] == label.negative_labels
        assert row[4] == label.description


@pytest.mark.parametrize(
    "create_func,table_name",
    [
        (create_documents_duckdb_table, "documents"),
        (create_passages_duckdb_table, "passages"),
        (create_labels_duckdb_table, "labels"),
    ],
)
def test_whether_table_handles_empty_list(tmp_path, create_func, table_name):
    db_path = tmp_path / f"test_{table_name}.duckdb"
    count = create_func(db_path, [])

    assert count == 0

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    conn.close()

    assert len(rows) == 0


@pytest.mark.parametrize(
    "create_func,table_name,test_data",
    [
        (create_documents_duckdb_table, "documents", "test_documents"),
        (create_passages_duckdb_table, "passages", "test_passages"),
        (create_labels_duckdb_table, "labels", "test_labels"),
    ],
)
def test_whether_table_overwrites_existing_table(
    tmp_path, create_func, table_name, test_data, request
):
    test_items = request.getfixturevalue(test_data)
    db_path = tmp_path / f"test_{table_name}.duckdb"

    create_func(db_path, [test_items[0]])
    count = create_func(db_path, test_items)

    assert count == len(test_items)

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    conn.close()

    assert len(rows) == len(test_items)


@pytest.mark.parametrize(
    "create_func,table_name,test_data",
    [
        (create_documents_duckdb_table, "documents", "test_documents"),
        (create_passages_duckdb_table, "passages", "test_passages"),
        (create_labels_duckdb_table, "labels", "test_labels"),
    ],
)
def test_whether_table_handles_large_batch(
    tmp_path, create_func, table_name, test_data, request
):
    test_items = request.getfixturevalue(test_data)
    db_path = tmp_path / f"test_{table_name}.duckdb"

    large_batch = test_items * 50
    count = create_func(db_path, large_batch)

    assert count == len(large_batch)

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    conn.close()

    assert len(rows) == len(large_batch)


def test_whether_passages_table_stores_array_types_correctly(tmp_path, test_passages):
    db_path = tmp_path / "test_passages.duckdb"
    create_passages_duckdb_table(db_path, test_passages)

    conn = duckdb.connect(str(db_path), read_only=True)

    columns = conn.execute("DESCRIBE passages").fetchall()
    labels_column = next(col for col in columns if col[0] == "labels")

    assert "VARCHAR[]" in labels_column[1].upper()

    rows = conn.execute("SELECT labels FROM passages LIMIT 1").fetchall()
    if rows:
        assert isinstance(rows[0][0], list)

    conn.close()


def test_whether_labels_table_stores_array_types_correctly(tmp_path, test_labels):
    db_path = tmp_path / "test_labels.duckdb"
    create_labels_duckdb_table(db_path, test_labels)

    conn = duckdb.connect(str(db_path), read_only=True)

    columns = conn.execute("DESCRIBE labels").fetchall()
    alt_labels_column = next(col for col in columns if col[0] == "alternative_labels")
    neg_labels_column = next(col for col in columns if col[0] == "negative_labels")

    assert "VARCHAR[]" in alt_labels_column[1].upper()
    assert "VARCHAR[]" in neg_labels_column[1].upper()

    rows = conn.execute(
        "SELECT alternative_labels, negative_labels FROM labels LIMIT 1"
    ).fetchall()
    if rows:
        assert isinstance(rows[0][0], list)
        assert isinstance(rows[0][1], list)

    conn.close()
