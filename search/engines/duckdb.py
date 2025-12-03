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
class TableSchema(Generic[T]):
    """Schema definition for a model's database table."""

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


class DocumentSchema(TableSchema[Document]):
    """Schema definition for a document's database table."""

    def __init__(self):
        super().__init__(
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
            title=row[0],
            source_url=row[1],
            description=row[2],
            original_document_id=row[3],
            labels=[],
        )


class PassageSchema(TableSchema[Passage]):
    """Schema definition for a passage's database table."""

    def __init__(self):
        super().__init__(
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
            text=row[0],
            document_id=row[1],
            labels=row[2],
            original_passage_id=row[3],
        )


class LabelSchema(TableSchema[Label]):
    """Schema definition for a label's database table."""

    def __init__(self):
        super().__init__(
            table_name="labels",
            create_sql="CREATE TABLE labels (id TEXT, preferred_label TEXT, alternative_labels TEXT[], negative_labels TEXT[], description TEXT)",
            insert_sql="INSERT INTO labels VALUES (?, ?, ?, ?, ?)",
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
        )

    def build_model(self, row: tuple) -> Label:
        """Build a label instance from a database row."""
        return Label(
            preferred_label=row[0],
            alternative_labels=row[1],
            negative_labels=row[2],
            description=row[3],
        )


class DuckDBSearchEngine(SearchEngine, Generic[TModel]):
    """Base search engine using DuckDB with parameterized queries."""

    schema: TableSchema[TModel]

    @overload
    def __init__(self, *, db_path: str | Path) -> None: ...

    @overload
    def __init__(self, *, items: Iterable[TModel]) -> None: ...

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        items: Iterable[TModel] | None = None,
    ) -> None:
        if db_path is None and items is None:
            raise ValueError("Either db_path or items must be provided")
        if db_path is not None and items is not None:
            raise ValueError("Only one of db_path or items must be provided")

        if db_path is not None:
            self.conn = duckdb.connect(str(db_path), read_only=True)
        else:
            self.conn = duckdb.connect(":memory:")
            self.conn.execute(self.schema.create_sql)

            # iterate over the supplied items and insert them in batches
            batch: list[tuple] = []
            for item in items:
                batch.append(self.schema.extract_row(item))

                if len(batch) >= DEFAULT_BATCH_SIZE:
                    self.conn.executemany(self.schema.insert_sql, batch)
                    batch.clear()

            if batch:
                self.conn.executemany(self.schema.insert_sql, batch)

    def search(self, terms: str) -> list[TModel]:
        """
        Search for items matching the terms.

        Uses parameterized queries to prevent SQL injection.
        """
        # Build WHERE clause with OR conditions for each search column
        where_conditions = " OR ".join(
            f"{col} ILIKE ?" for col in self.schema.searchable_columns
        )

        query = f"""
            SELECT * FROM {self.schema.table_name}
            WHERE {where_conditions}
        """

        # Create LIKE pattern with wildcards
        pattern = f"%{terms}%"
        params = [pattern] * len(self.schema.searchable_columns)

        results = self.conn.execute(query, params).fetchall()
        return [self.schema.build_model(row) for row in results]


class DuckDBDocumentSearchEngine(DuckDBSearchEngine[Document], DocumentSearchEngine):
    """Search engine for documents."""

    schema = DocumentSchema()


class DuckDBPassageSearchEngine(DuckDBSearchEngine[Passage], PassageSearchEngine):
    """Search engine for passages."""

    schema = PassageSchema()


class DuckDBLabelSearchEngine(DuckDBSearchEngine[Label], LabelSearchEngine):
    """Search engine for labels."""

    schema = LabelSchema()

    def search(self, terms: str) -> list[Label]:
        """
        Search for labels, including array column checks.

        Extends base search to check alternative_labels array.
        """
        # Base search on text columns
        query = """
            SELECT * FROM labels
            WHERE preferred_label ILIKE ?
                OR description ILIKE ?
                OR list_has_any(alternative_labels, ?)
        """

        pattern = f"%{terms}%"
        results = self.conn.execute(query, [pattern, pattern, [terms]]).fetchall()
        return [self.schema.build_model(row) for row in results]
