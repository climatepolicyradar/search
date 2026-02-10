import json

import requests

from search.engines import SearchEngine
from search.log import get_logger
from search.data_in_models import Document, DocumentLabelRelationship, Label

logger = get_logger(__name__)

"""
This class should be using the Vespa Client, but we are having problems connecting to the remote server
because of the way API Gateway handles trailing slashes.

i.e.
VespaClient connects to `/search/`.
This isn't a viable URL for API Gatewayway, you can use
- `/search`
- `/search/{proxy+}`

The secondary URL uses a `+` which matches 1 or more characters. 🤷

For now we just use `requests` which yields the same results.
"""

API_TIMEOUT = 1  # seconds
API_URL = "https://vz0k397ock.execute-api.eu-west-1.amazonaws.com/production"
# We make this very obvious as it is used for values that should exist
MISSING_PLACEHOLDER = "MISSING"


class DevVespaDocumentSearchEngine(SearchEngine[Document]):
    """Search engine for dev Vespa"""

    def __init__(self) -> None:
        pass

    def search(
        self, terms: str, limit: int | None = None, offset: int = 0
    ) -> list[Document]:
        """Fetch a list of relevant search results."""
        if limit is None:
            limit = 10

        yql = "select * from sources documents where userQuery()"

        try:
            res = requests.post(
                f"{API_URL}/search",
                json={
                    "yql": yql,
                    "query": terms,
                    "hits": limit,
                    "offset": offset,
                },
                timeout=API_TIMEOUT,
            )
        except Exception:
            logger.exception("Vespa query failed")
            return []

        res = res.json()
        documents = []

        for hit in res.get("root").get("children"):
            fields = hit.get("fields", {})
            # Map fields. Note: schema only has title, description.
            # source_url and original_document_id are required by Document.
            # We'll use the doc id for original_document_id and a dummy/empty source_url if missing.
            source = json.loads(fields.get("source"))
            labels = []
            for label in source.get("labels", []):
                labels.append(
                    DocumentLabelRelationship(
                        type=label.get("type", MISSING_PLACEHOLDER),
                        label=Label(
                            id=label.get("label").get("id", MISSING_PLACEHOLDER),
                            title=label.get("label").get("title", MISSING_PLACEHOLDER),
                            type=label.get("label").get("type", MISSING_PLACEHOLDER),
                        ),
                        timestamp=label.get("timestamp"),
                    )
                )
            documents.append(
                Document(
                    id=hit.get("id", "unknown"),
                    title=source.get("title", "No Title"),
                    description=source.get("description"),
                    labels=labels,
                )
            )

        return documents

    def count(self, terms: str) -> int:
        """Return hit count"""
        raise NotImplementedError()
