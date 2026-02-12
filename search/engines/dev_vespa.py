import json
import re

import requests

from search.data_in_models import Document, DocumentLabelRelationship, Label
from search.log import get_logger

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

API_TIMEOUT = 5  # seconds
API_URL = "https://vz0k397ock.execute-api.eu-west-1.amazonaws.com/production"
# We make this very obvious as it is used for values that should exist
MISSING_PLACEHOLDER = "MISSING"


# We do not inherit from `SearchEngine[Document]` as the search method has different parameters.
# At least for now.
class DevVespaDocumentSearchEngine:
    """Search engine for dev Vespa"""

    def __init__(self) -> None:
        pass

    def search(
        self, query: str | None, where: str, limit: int, offset: int = 0
    ) -> list[Document]:
        """Fetch a list of relevant search results."""

        yql = f"select * from sources documents where {where}"
        if query:
            yql += " and userQuery()"
        yql += f" limit {limit} offset {offset}"

        try:
            res = requests.post(
                f"{API_URL}/search",
                json={
                    "yql": yql,
                    "query": query,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
            )
        except Exception:
            logger.exception("Vespa query failed")
            return []

        res = res.json()
        documents = []

        print(where)
        # print(query)
        # print(res)

        for hit in res.get("root").get("children", []):
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

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()


# We do not inherit from `SearchEngine[Label]` as the searech method does not have `limit: int, offset: int` parameters
# at least not yet
class DevVespaLabelSearchEngine:
    """Search engine for dev Vespa"""

    def __init__(self) -> None:
        pass

    def search(self, query: str) -> list[Label]:
        """Fetch a list of relevant search results."""

        # 1) prefix filter the documents list on `labels_title_attribute` to ensure we are grouping by as few documents as possible for performance
        # We use `matches` with a case-insensitive regex pattern `(?i)` because `contains` on attributes is strictly case-sensitive.
        safe_terms = re.escape(query)
        doc_regex = f"(?i)^{safe_terms}.*"
        document_filter_query = f'select * from sources documents where labels_title_attribute matches "{doc_regex}"'

        # 2) group by all `labels_title_attribute` values that match the prefix
        grouping_query = "group(labels_title_attribute)"

        # 3) filter the group
        group_filter_query = f'filter(regex("{doc_regex}", labels_title_attribute))'

        # 4) limit and order and output the groups
        group_order_query = "order(-count()) each(output(count()))"

        yql = f"{document_filter_query} | all({grouping_query} {group_filter_query} {group_order_query})"

        try:
            res = requests.post(
                f"{API_URL}/search",
                json={
                    "yql": yql,
                    "query": query,
                    # standard practice is "hits": 0 to get only aggregation if possible
                    "hits": 0,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
            )
        except Exception:
            logger.exception("Vespa query failed")
            return []

        res = res.json()
        labels = []

        # From the YQL above - the structure is typically: `root.children[0].children[0].children[]`
        root = res.get("root", {})

        children = root.get("children", [{}])[0].get("children", [])
        group_list = next(
            (
                item.get("children", [])
                for item in children
                if item.get("label") == "labels_title_attribute"
            ),
            [],
        )

        for group in group_list:
            label_title = group.get("value", "")
            labels.append(
                Label(
                    id=label_title,
                    title=label_title,
                    type="aggregated",  # Type is lost in aggregation
                )
            )

        return labels

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()
