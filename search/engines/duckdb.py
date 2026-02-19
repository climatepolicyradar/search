from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar, overload

import duckdb
from pydantic import BaseModel

from search.document import Document
from search.engines import (
    DocumentSearchEngine,
    LabelSearchEngine,
    PassageSearchEngine,
    SearchEngine,
    TModel,
)
from search.label import Label
from search.passage import Passage

DEFAULT_BATCH_SIZE = 10_000

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class DuckDBTableSchema(Generic[T]):
    """Schema definition for a model's database table."""

    model_class: type[T]
    table_name: str
    create_sql: str
    insert_sql: str
    searchable_columns: list[str]

    def extract_row(self, item: T) -> tuple:
        """Extract a row tuple from a model instance."""
        raise NotImplementedError

    def build_model(self, row: tuple) -> T:
        """Build a model instance from a database row."""
        raise NotImplementedError


class DuckDBDocumentTableSchema(DuckDBTableSchema[Document]):
    """Schema definition for a document's database table."""

    def __init__(self):
        super().__init__(
            model_class=Document,
            table_name="documents",
            create_sql="CREATE TABLE documents (id TEXT, title TEXT, source_url TEXT, description TEXT, original_document_id TEXT)",
            insert_sql="INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
            searchable_columns=["title", "description"],
        )

    def extract_row(self, item: Document) -> tuple:
        """Extract a row tuple from a document instance."""
        return (
            item.id,
            item.title,
            str(item.source_url),
            item.description,
            item.original_document_id,
        )

    def build_model(self, row: tuple) -> Document:
        """Build a document instance from a database row."""
        return Document(
            title=row[1],
            source_url=row[2],
            description=row[3],
            original_document_id=row[4],
            labels=[],
        )


class DuckDBPassageTableSchema(DuckDBTableSchema[Passage]):
    """Schema definition for a passage's database table."""

    def __init__(self):
        super().__init__(
            model_class=Passage,
            table_name="passages",
            create_sql="CREATE TABLE passages (id TEXT, text TEXT, document_id TEXT, labels TEXT[], original_passage_id TEXT)",
            insert_sql="INSERT INTO passages VALUES (?, ?, ?, ?, ?)",
            searchable_columns=["text"],
        )

    def extract_row(self, item: Passage) -> tuple:
        """Extract a row tuple from a passage instance."""
        return (
            item.id,
            item.text,
            item.document_id,
            item.labels,
            item.original_passage_id,
        )

    def build_model(self, row: tuple) -> Passage:
        """Build a passage instance from a database row."""
        return Passage(
            text=row[1],
            document_id=row[2],
            labels=row[3],
            original_passage_id=row[4],
        )


class DuckDBLabelTableSchema(DuckDBTableSchema[Label]):
    """Schema definition for a label's database table."""

    def __init__(self):
        super().__init__(
            model_class=Label,
            table_name="labels",
            create_sql="CREATE TABLE labels (id TEXT, preferred_label TEXT, alternative_labels TEXT[], negative_labels TEXT[], description TEXT, source TEXT, id_at_source TEXT)",
            insert_sql="INSERT INTO labels VALUES (?, ?, ?, ?, ?, ?, ?)",
            searchable_columns=["preferred_label", "description"],
        )

    def extract_row(self, item: Label) -> tuple:
        """Extract a row tuple from a label instance."""
        return (
            item.id,
            item.preferred_label,
            item.alternative_labels,
            item.negative_labels,
            item.description,
            item.source,
            item.id_at_source,
        )

    def build_model(self, row: tuple) -> Label:
        """Build a label instance from a database row."""
        return Label(
            preferred_label=row[1],
            alternative_labels=row[2],
            negative_labels=row[3],
            description=row[4],
            source=row[5],
            id_at_source=row[6],
        )


def create_duckdb_table(
    schema: DuckDBTableSchema[T],
    items: Iterable[T],
    output_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Create and populate a DuckDB table file from items.

    :param schema: The table schema defining structure and insert operations
    :param items: Iterable of model instances to insert into the database
    :param output_path: Path where the DuckDB file will be created
    :param batch_size: Maximum number of items to accumulate before executing batch insert
    :return: Total number of items inserted into the database
    """
    conn = duckdb.connect(str(output_path))
    conn.execute(schema.create_sql)

    batch: list[tuple] = []
    total_count = 0

    for item in items:
        batch.append(schema.extract_row(item))
        total_count += 1

        if len(batch) >= batch_size:
            conn.executemany(schema.insert_sql, batch)
            batch.clear()

    if batch:
        conn.executemany(schema.insert_sql, batch)

    conn.close()
    return total_count


def create_documents_duckdb_table(
    output_path: Path,
    documents: Iterable[Document],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Create and populate a DuckDB table file with documents.

    :param output_path: Path where the DuckDB file will be created
    :param documents: Iterable of Document instances to insert
    :param batch_size: Maximum number of items to accumulate before executing batch insert
    :return: Total number of documents inserted into the database
    """
    return create_duckdb_table(
        DuckDBDocumentTableSchema(), documents, output_path, batch_size
    )


def create_labels_duckdb_table(
    output_path: Path,
    labels: Iterable[Label],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Create and populate a DuckDB table file with labels.

    :param output_path: Path where the DuckDB file will be created
    :param labels: Iterable of Label instances to insert
    :param batch_size: Maximum number of items to accumulate before executing batch insert
    :return: Total number of labels inserted into the database
    """
    return create_duckdb_table(
        DuckDBLabelTableSchema(), labels, output_path, batch_size
    )


def create_passages_duckdb_table(
    output_path: Path,
    passages: Iterable[Passage],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Create and populate a DuckDB table file with passages.

    :param output_path: Path where the DuckDB file will be created
    :param passages: Iterable of Passage instances to insert
    :param batch_size: Maximum number of items to accumulate before executing batch insert
    :return: Total number of passages inserted into the database
    """
    return create_duckdb_table(
        DuckDBPassageTableSchema(), passages, output_path, batch_size
    )


class DuckDBSearchEngine(SearchEngine, Generic[TModel]):
    """Base search engine using DuckDB with parameterized queries."""

    schema: DuckDBTableSchema[TModel]

    def _insert_items(self, items: Iterable[TModel], batch_size: int) -> None:
        """
        Insert items into the database in batches.

        :param items: Items to insert
        :param batch_size: Number of items to insert per batch
        """
        batch: list[tuple] = []
        for item in items:
            batch.append(self.schema.extract_row(item))

            if len(batch) >= batch_size:
                self.conn.executemany(self.schema.insert_sql, batch)
                batch.clear()

        if batch:
            self.conn.executemany(self.schema.insert_sql, batch)

    @overload
    def __init__(self, *, db_path: str | Path) -> None: ...

    @overload
    def __init__(
        self, *, items: Iterable[TModel], batch_size: int = DEFAULT_BATCH_SIZE
    ) -> None: ...

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        items: Iterable[TModel] | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        if db_path is not None and items is not None:
            raise ValueError("db_path and items are mutually exclusive")

        if db_path is None and items is None:
            raise ValueError("Either db_path or items must be provided")

        if db_path is not None:
            # Read-only mode: open existing file
            self.conn = duckdb.connect(str(db_path), read_only=True)
        elif items is not None:
            self.conn = duckdb.connect(":memory:")
            self.conn.execute(self.schema.create_sql)
            self._insert_items(items, batch_size)

    def search(
        self, terms: str, limit: int | None = None, offset: int = 0
    ) -> list[TModel]:
        """
        Search for items matching the terms.

        Uses parameterised queries to prevent SQL injection.
        """

        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        # Build WHERE clause with OR conditions for each search column
        where_conditions = " OR ".join(
            f"{col} ILIKE ?" for col in self.schema.searchable_columns
        )

        # Build base query
        query = f"""
            SELECT * FROM {self.schema.table_name}
            WHERE {where_conditions}
        """

        # Add pagination clauses
        if limit is not None:
            query += f" LIMIT {limit}"
        if offset > 0:
            query += f" OFFSET {offset}"

        # Create LIKE pattern with wildcards
        pattern = f"%{terms}%"
        params = [pattern] * len(self.schema.searchable_columns)

        results = self.conn.execute(query, params).fetchall()
        return [self.schema.build_model(row) for row in results]

    def count(self, terms: str) -> int:
        """Count total number of items matching the search terms."""

        where_conditions = " OR ".join(
            f"{col} ILIKE ?" for col in self.schema.searchable_columns
        )

        query = f"""
            SELECT COUNT(*) FROM {self.schema.table_name}
            WHERE {where_conditions}
        """

        # Create LIKE pattern with wildcards
        pattern = f"%{terms}%"
        params = [pattern] * len(self.schema.searchable_columns)

        result = self.conn.execute(query, params).fetchone()
        return result[0] if result else 0


class DuckDBDocumentSearchEngine(DuckDBSearchEngine[Document], DocumentSearchEngine):
    """Search engine for documents."""

    schema = DuckDBDocumentTableSchema()


class DuckDBPassageSearchEngine(DuckDBSearchEngine[Passage], PassageSearchEngine):
    """Search engine for passages."""

    schema = DuckDBPassageTableSchema()


class DuckDBLabelSearchEngine(DuckDBSearchEngine[Label], LabelSearchEngine):
    """Search engine for labels."""

    schema = DuckDBLabelTableSchema()

    def search(
        self, terms: str, limit: int | None = None, offset: int = 0
    ) -> list[Label]:
        """
        Search for labels, including array column checks.

        Extends base search to check alternative_labels array.
        """
        # Validate inputs
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        # Base search on text columns plus array column
        query = """
            SELECT * FROM labels
            WHERE preferred_label ILIKE ?
                OR description ILIKE ?
                OR list_has_any(alternative_labels, ?)
        """

        # Add pagination clauses
        if limit is not None:
            query += f" LIMIT {limit}"
        if offset > 0:
            query += f" OFFSET {offset}"

        pattern = f"%{terms}%"
        results = self.conn.execute(query, [pattern, pattern, [terms]]).fetchall()
        return [self.schema.build_model(row) for row in results]

    def count(self, query: str) -> int:
        """Count total number of labels matching the search query."""

        query = """
            SELECT COUNT(*) FROM labels
            WHERE preferred_label ILIKE ?
                OR description ILIKE ?
                OR list_has_any(alternative_labels, ?)
        """

        pattern = f"%{query}%"
        result = self.conn.execute(query, [pattern, pattern, [query]]).fetchone()
        return result[0] if result else 0
