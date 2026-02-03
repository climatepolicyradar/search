from typing import cast

from pydantic import AnyHttpUrl

from search.document import Document
from search.engines import DocumentSearchEngine
from search.log import get_logger
from vespa.application import Vespa
from vespa.io import VespaQueryResponse

logger = get_logger(__name__)


class LocalVespaSearchEngine(DocumentSearchEngine):
    """Search engine for local Vespa"""

    def __init__(self) -> None:
        self.client = Vespa(url="http://localhost:8000")

    def search(
        self, terms: str, limit: int | None = None, offset: int = 0
    ) -> list[Document]:
        """Fetch a list of relevant search results."""
        if limit is None:
            limit = 10

        yql = "select * from sources documents where userQuery()"

        try:
            res = self.client.query(
                body={
                    "yql": yql,
                    "query": terms,
                    "hits": limit,
                    "offset": offset,
                }
            )
        except Exception:
            logger.exception("Vespa query failed")
            return []

        res = cast(VespaQueryResponse, res)
        documents = []
        for hit in res.hits:
            fields = hit.get("fields", {})
            # Map fields. Note: schema only has title, description.
            # source_url and original_document_id are required by Document.
            # We'll use the doc id for original_document_id and a dummy/empty source_url if missing.

            documents.append(
                Document(
                    title=fields.get("title", "No Title"),
                    description=fields.get("description", ""),
                    source_url=AnyHttpUrl(
                        "http://localhost"
                    ),  # Placeholder as not in schema
                    original_document_id=hit.get("id", "unknown"),
                    labels=[],
                )
            )

        return documents

    def count(self, terms: str) -> int:
        """Count total number of results matching the search terms."""
        yql = "select * from sources documents where userQuery()"
        res = self.client.query(
            body={
                "yql": yql,
                "query": terms,
                "hits": 0,
            }
        )
        res = cast(VespaQueryResponse, res)
        return res.number_documents_retrieved
