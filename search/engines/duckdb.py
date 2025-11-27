from typing import TypeVar

import duckdb
from pydantic import BaseModel

from search.document import Document
from search.engines import DocumentSearchEngine, LabelSearchEngine, PassageSearchEngine
from search.label import Label
from search.passage import Passage

T = TypeVar("T", bound=BaseModel)


class DuckDBSearchEngine:
    """Base class for DuckDB search engines."""

    def __init__(self, db_path: str):
        """Initialize the DuckDB search engine with a read-only connection."""
        self.db_path = db_path
        self.conn = duckdb.connect(db_path, read_only=True)

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
                labels
            FROM passages
            WHERE text ILIKE '%{escaped_terms}%'
        """

        results = self._execute_search(query)

        return [
            Passage(
                text=row[0],
                document_id=row[1],
                labels=row[2],
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
