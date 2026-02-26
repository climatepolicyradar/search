from __future__ import annotations

import json
import re
from typing import Literal

import requests
from pydantic import BaseModel
from pydantic.networks import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from search.data_in_models import Document, Label, LabelRelationship
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
# We make this very obvious as it is used for values that should exist
MISSING_PLACEHOLDER = "MISSING"


# region Settings
class Settings(BaseSettings):
    vespa_endpoint: AnyHttpUrl
    vespa_read_token: str
    model_config = SettingsConfigDict(env_file="api/.env")


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = Settings()  # pyright: ignore[reportCallIssue]

# endregion


# region Filters
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
    field = "labels_value_attribute"
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
        filters_json_string: str | None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Document]:
        """Fetch a list of relevant search results."""
        where = "true "

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
                f"{settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "query": query,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {settings.vespa_read_token}",
                },
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
                    LabelRelationship(
                        type=label.get("type", MISSING_PLACEHOLDER),
                        value=Label(
                            id=label.get("label").get("id", MISSING_PLACEHOLDER),
                            value=label.get("label").get("value", MISSING_PLACEHOLDER),
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

        # 1) prefix filter the documents list on `labels_value_attribute` to ensure we are grouping by as few documents as possible for performance
        # We use `matches` with a case-insensitive regex pattern `(?i)` because `contains` on attributes is strictly case-sensitive.
        safe_terms = re.escape(query)
        doc_regex = f"(?i)^{safe_terms}.*"
        document_filter_query = f'select * from sources documents where labels_value_attribute matches "{doc_regex}"'

        # 2) group by all `labels_value_attribute` values that match the prefix
        grouping_query = "group(labels_value_attribute)"

        # 3) filter the group
        group_filter_query = f'filter(regex("{doc_regex}", labels_value_attribute))'

        # 4) limit and order and output the groups
        group_order_query = "order(-count()) each(output(count()))"

        yql = f"{document_filter_query} | all({grouping_query} {group_filter_query} {group_order_query})"

        try:
            res = requests.post(
                f"{settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "query": query,
                    # standard practice is "hits": 0 to get only aggregation if possible
                    "hits": 0,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {settings.vespa_read_token}",
                },
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
                if item.get("label") == "labels_value_attribute"
            ),
            [],
        )

        for group in group_list:
            label_title = group.get("value", "")
            labels.append(
                Label(
                    id=label_title,
                    value=label_title,
                    type="aggregated",  # Type is lost in aggregation
                )
            )

        return labels

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()
