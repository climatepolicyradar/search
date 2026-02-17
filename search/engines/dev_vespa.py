import json
import re
from typing import Literal

import requests
from pydantic import BaseModel, TypeAdapter

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


# region filters
class FilterCondition(BaseModel):
    field: Literal["labels.label.id"]
    operator: Literal["contains", "not_contains"]
    value: list[str]


class Filter(BaseModel):
    operator: Literal["or", "and"]
    conditions: list[FilterCondition]


def _build_filter_query(filters: list[Filter]) -> str:
    query_to_search_field_map = {
        "labels.label.id": "labels_title_attribute",
    }

    where = ""
    for filter_group in filters:
        conditions_list = []
        for condition in filter_group.conditions:
            field = query_to_search_field_map.get(condition.field)
            values = condition.value

            if condition.operator == "not_contains":
                sub_clauses = [f'!({field} contains "{v}")' for v in values]
                join_op = " and "
            else:
                sub_clauses = [f'{field} contains "{v}"' for v in values]
                join_op = " or "

            if sub_clauses:
                clause = (
                    f"({join_op.join(sub_clauses)})"
                    if len(sub_clauses) > 1
                    else sub_clauses[0]
                )
                conditions_list.append(clause)

        if conditions_list:
            join_op = f" {filter_group.operator} "
            where += f" and ({join_op.join(conditions_list)})"

    return where


def _build_labels_label_id_filter(
    labels_id_and: list[str] | None,
    labels_id_or: list[str] | None,
    labels_id_not: list[str] | None,
):
    where = ""

    """
    This query is resolved to:
    (OR filters) AND (AND filters) AND (...NOT filters)
    """

    if labels_id_or:
        where += f" and ({' or '.join([f'labels_title_attribute contains \"{label}\"' for label in labels_id_or])})"

    if labels_id_and:
        where += "".join(
            [
                f' and labels_title_attribute contains "{label}"'
                for label in labels_id_and
            ]
        )

    if labels_id_not:
        where += "".join(
            [
                f' and ! (labels_title_attribute contains "{label}")'
                for label in labels_id_not
            ]
        )

    return where


# endregion


# We do not inherit from `SearchEngine[Document]` as the search method has different parameters.
# At least for now.
class DevVespaDocumentSearchEngine:
    """Search engine for dev Vespa"""

    def __init__(self) -> None:
        pass

    def search(
        self,
        query: str | None,
        labels_id_and: list[str] | None,
        labels_id_or: list[str] | None,
        labels_id_not: list[str] | None,
        filters_json_string: str | None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Document]:
        """Fetch a list of relevant search results."""
        where = "true "

        where += _build_labels_label_id_filter(
            labels_id_and=labels_id_and,
            labels_id_or=labels_id_or,
            labels_id_not=labels_id_not,
        )

        if filters_json_string:
            filters = TypeAdapter(list[Filter]).validate_json(filters_json_string)
            where += _build_filter_query(filters)

        yql = f"select * from sources documents where {where}"
        if query:
            yql += " and userQuery()"
        yql += f" limit {limit} offset {offset}"
        print(f"searching for yql: {yql}")
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
                    id=hit.get("id", MISSING_PLACEHOLDER),
                    title=source.get("title", MISSING_PLACEHOLDER),
                    description=source.get("description", MISSING_PLACEHOLDER),
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
