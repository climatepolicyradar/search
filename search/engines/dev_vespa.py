from __future__ import annotations

import json
import re
from typing import Literal

import requests
from pydantic import BaseModel

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


class LabelsCondition(BaseModel):
    field: Literal["labels.label.id"]
    op: Literal["contains", "not_contains"]
    value: str


Condition = LabelsCondition


class Filter(BaseModel):
    """A group of filters combined with AND or OR. Supports arbitrary nesting."""

    op: Literal["and", "or"]
    filters: list[Condition | Filter]


# Simple example: label contains "Romania"
SimpleExampleFilter = Filter(
    op="and",
    filters=[
        LabelsCondition(
            field="labels.label.id",
            op="contains",
            value="Romania",
        ),
    ],
)

# Complex example: ((label contains "Multilateral climate fund project" AND label contain "Principal") OR label contains "UN") AND label contains "Romania"
ComplexExampleFilter = Filter(
    op="and",
    filters=[
        Filter(
            op="or",
            filters=[
                Filter(
                    op="and",
                    filters=[
                        LabelsCondition(
                            field="labels.label.id",
                            op="contains",
                            value="Multilateral climate fund project",
                        ),
                        LabelsCondition(
                            field="labels.label.id",
                            op="contains",
                            value="Principal",
                        ),
                    ],
                ),
                LabelsCondition(
                    field="labels.label.id",
                    op="contains",
                    value="UN submissions",
                ),
            ],
        ),
        LabelsCondition(
            field="labels.label.id",
            op="contains",
            value="Romania",
        ),
    ],
)


def _build_condition_yql(condition: Condition) -> str:
    """Build YQL for a single condition (labels only for now)."""
    field = "labels_title_attribute"
    value = condition.value
    if condition.op == "not_contains":
        return f'!({field} contains "{value}")'
    else:
        return f'{field} contains "{value}"'


def _build_filter_yql(filter_group: Filter) -> str:
    """Recursively build YQL for a filter group."""
    parts: list[str] = []

    for item in filter_group.filters:
        if isinstance(item, Filter):
            # Recurse into nested group
            parts.append(_build_filter_yql(item))
        else:
            # It's a Condition
            parts.append(_build_condition_yql(item))

    if not parts:
        return ""

    join_op = f" {filter_group.op} "
    joined = join_op.join(parts)

    # Wrap in parentheses if multiple parts
    return f"({joined})" if len(parts) > 1 else joined


def _build_filter_query(filter_group: Filter | None) -> str:
    """Build the WHERE clause from a filter group."""
    if filter_group is None:
        return ""
    yql = _build_filter_yql(filter_group)
    return f" and {yql}" if yql else ""


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
            filters = Filter.model_validate_json(filters_json_string)
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
