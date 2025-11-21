import duckdb

from search.engines import LabelSearchEngine
from search.label import Label


class DuckDBLabelSearchEngine(LabelSearchEngine):
    """A search engine that searches for labels in a DuckDB database."""

    def __init__(self, db_path: str):
        """Initialize the DuckDB label search engine."""
        self.db_path = db_path
        self.conn = duckdb.connect(db_path, read_only=True)

    def search(self, terms: str) -> list[Label]:
        """
        Fetch a list of relevant labels matching the search terms.

        Searches across preferred_label, alternative_labels, and description.

        :param str terms: The search terms
        :return list[Label]: A list of matching labels
        """
        escaped_terms = terms.replace("'", "''")

        results = self.conn.execute(
            f"""
            SELECT DISTINCT
                preferred_label,
                alternative_labels,
                negative_labels,
                description
            FROM labels
            WHERE preferred_label ILIKE '%{escaped_terms}%'
                OR description ILIKE '%{escaped_terms}%'
                OR list_contains(alternative_labels, '{escaped_terms}')
            """,
        ).fetchall()

        labels = []
        for row in results:
            labels.append(
                Label(
                    preferred_label=row[0],
                    alternative_labels=row[1],
                    negative_labels=row[2],
                    description=row[3],
                )
            )

        return labels
