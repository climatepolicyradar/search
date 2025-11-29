from collections.abc import Iterable
from pathlib import Path
from typing import Callable, TypeVar

import duckdb

from search.document import Document
from search.engines import DocumentSearchEngine, LabelSearchEngine, PassageSearchEngine
from search.label import Label
from search.passage import Passage

T = TypeVar("T")

DEFAULT_BATCH_SIZE = 10_000


def _create_duckdb_table(
    db_path: Path,
    create_table_sql: str,
    insert_sql: str,
    items: Iterable[T],
    row_extractor: Callable[[T], tuple],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Generic function to create a DuckDB table and insert data.

    Processes items in batches to avoid memory issues with large datasets.

    Args:
        db_path: Path to the DuckDB database file
        create_table_sql: SQL statement to create the table
        insert_sql: SQL statement to insert rows (with ? placeholders)
        items: Iterable of items to insert (can be a generator)
        row_extractor: Function that extracts a tuple of values from each item
        batch_size: Number of items to insert per batch

    Returns:
        Total number of items inserted
    """
    db_path.unlink(missing_ok=True)
    conn = duckdb.connect(db_path)
    conn.execute(create_table_sql)

    total_count = 0
    batch: list[tuple] = []

    for item in items:
        batch.append(row_extractor(item))

        if len(batch) >= batch_size:
            conn.executemany(insert_sql, batch)
            total_count += len(batch)
            batch.clear()

    # Insert remaining items
    if batch:
        conn.executemany(insert_sql, batch)
        total_count += len(batch)

    conn.close()
    return total_count


def create_documents_duckdb_table(db_path: Path, documents: Iterable[Document]) -> int:
    """
    Create a DuckDB table for documents and insert the provided documents.

    Args:
        db_path: Path to the DuckDB database file
        documents: Iterable of Document objects to insert

    Returns:
        Total number of documents inserted
    """
    return _create_duckdb_table(
        db_path=db_path,
        create_table_sql="CREATE TABLE documents (id TEXT, title TEXT, source_url TEXT, description TEXT, original_document_id TEXT)",
        insert_sql="INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
        items=documents,
        row_extractor=lambda doc: (
            doc.id,
            doc.title,
            str(doc.source_url),
            doc.description,
            doc.original_document_id,
        ),
    )


def create_passages_duckdb_table(db_path: Path, passages: Iterable[Passage]) -> int:
    """
    Create a DuckDB table for passages and insert the provided passages.

    Args:
        db_path: Path to the DuckDB database file
        passages: Iterable of Passage objects to insert

    Returns:
        Total number of passages inserted
    """
    return _create_duckdb_table(
        db_path=db_path,
        create_table_sql="CREATE TABLE passages (id TEXT, text TEXT, document_id TEXT, labels TEXT[], original_passage_id TEXT)",
        insert_sql="INSERT INTO passages VALUES (?, ?, ?, ?, ?)",
        items=passages,
        row_extractor=lambda passage: (
            passage.id,
            passage.text,
            passage.document_id,
            passage.labels,
            passage.original_passage_id,
        ),
    )


def create_labels_duckdb_table(db_path: Path, labels: Iterable[Label]) -> int:
    """
    Create a DuckDB table for labels and insert the provided labels.

    Args:
        db_path: Path to the DuckDB database file
        labels: Iterable of Label objects to insert

    Returns:
        Total number of labels inserted
    """
    return _create_duckdb_table(
        db_path=db_path,
        create_table_sql="CREATE TABLE labels (id TEXT, preferred_label TEXT, alternative_labels TEXT[], negative_labels TEXT[], description TEXT)",
        insert_sql="INSERT INTO labels VALUES (?, ?, ?, ?, ?)",
        items=labels,
        row_extractor=lambda label: (
            label.id,
            label.preferred_label,
            label.alternative_labels,
            label.negative_labels,
            label.description,
        ),
    )


class DuckDBSearchEngine:
    """Base class for DuckDB search engines."""

    def __init__(self, db_path: str | Path):
        """Initialize the DuckDB search engine with a read-only connection."""
        self.conn = duckdb.connect(str(db_path), read_only=True)

    def _escape_terms(self, terms: str) -> str:
        """Escape single quotes in search terms for SQL safety."""
        return terms.replace("'", "''")

    def _execute_search(self, query: str) -> list[tuple]:
        """Execute a search query and return results."""
        return self.conn.execute(query).fetchall()


class DuckDBLabelSearchEngine(DuckDBSearchEngine, LabelSearchEngine):
    """A search engine that searches for labels in a DuckDB database."""

    def search(self, terms: str) -> list[Label]:
        """
        Fetch a list of relevant labels matching the search terms.

        Searches across preferred_label, alternative_labels, and description.

        :param str terms: The search terms
        :return list[Label]: A list of matching labels
        """
        escaped_terms = self._escape_terms(terms)

        query = f"""
            SELECT DISTINCT
                preferred_label,
                alternative_labels,
                negative_labels,
                description
            FROM labels
            WHERE preferred_label ILIKE '%{escaped_terms}%'
                OR description ILIKE '%{escaped_terms}%'
                OR list_contains(alternative_labels, '{escaped_terms}')
        """

        results = self._execute_search(query)

        return [
            Label(
                preferred_label=row[0],
                alternative_labels=row[1],
                negative_labels=row[2],
                description=row[3],
            )
            for row in results
        ]


class DuckDBPassageSearchEngine(DuckDBSearchEngine, PassageSearchEngine):
    """A search engine that searches for passages in a DuckDB database."""

    def search(self, terms: str) -> list[Passage]:
        """
        Fetch a list of relevant passages matching the search terms.

        Searches across passage text (case-insensitive).

        :param str terms: The search terms
        :return list[Passage]: A list of matching passages
        """
        escaped_terms = self._escape_terms(terms)

        query = f"""
            SELECT DISTINCT
                text,
                document_id,
                labels,
                original_passage_id
            FROM passages
            WHERE text ILIKE '%{escaped_terms}%'
        """

        results = self._execute_search(query)

        return [
            Passage(
                text=row[0],
                document_id=row[1],
                labels=row[2],
                original_passage_id=row[3],
            )
            for row in results
        ]


class DuckDBDocumentSearchEngine(DuckDBSearchEngine, DocumentSearchEngine):
    """A search engine that searches for documents in a DuckDB database."""

    def search(self, terms: str) -> list[Document]:
        """
        Fetch a list of relevant documents matching the search terms.

        Searches across title and description (case-insensitive).

        :param str terms: The search terms
        :return list[Document]: A list of matching documents
        """
        escaped_terms = self._escape_terms(terms)

        query = f"""
            SELECT DISTINCT
                title,
                source_url,
                description,
                labels,
                passages
            FROM documents
            WHERE title ILIKE '%{escaped_terms}%'
                OR description ILIKE '%{escaped_terms}%'
        """

        results = self._execute_search(query)

        return [
            Document(
                title=row[0],
                source_url=row[1],
                description=row[2],
                labels=row[3],
                passages=row[4],
            )
            for row in results
        ]
