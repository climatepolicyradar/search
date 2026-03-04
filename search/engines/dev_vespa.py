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

# endregion Settings


# region Filters
class LabelsCondition(BaseModel):
    field: Literal["labels.value.id"]
    op: Literal["contains", "not_contains"]
    value: str


class AttributesCondition(BaseModel):
    field: Literal["attributes_string", "attributes_double", "attributes_boolean"]
    key: str
    op: Literal["eq", "not_eq"]
    value: str | float | bool


Condition = LabelsCondition | AttributesCondition


class Filter(BaseModel):
    """A group of filters combined with AND or OR. Supports arbitrary nesting."""

    op: Literal["and", "or"]
    filters: list[Condition | Filter]


# Simple example: label contains "Romania"
SimpleExampleFilter = Filter(
    op="and",
    filters=[
        LabelsCondition(
            field="labels.value.id",
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
                            field="labels.value.id",
                            op="contains",
                            value="Multilateral climate fund project",
                        ),
                        LabelsCondition(
                            field="labels.value.id",
                            op="contains",
                            value="Principal",
                        ),
                    ],
                ),
                LabelsCondition(
                    field="labels.value.id",
                    op="contains",
                    value="UN submissions",
                ),
            ],
        ),
        LabelsCondition(
            field="labels.value.id",
            op="contains",
            value="Romania",
        ),
        AttributesCondition(
            field="attributes_double",
            key="project_cost_usd",
            op="eq",
            value=1000000.0,
        ),
    ],
)


def _format_value(value: str | float | bool) -> str:
    """Format a value for YQL: strings get quotes, numbers do not, bools become 1/0 (byte)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


def _build_condition_yql(condition: Condition) -> str:
    match condition:
        case AttributesCondition():
            # Using `sameElement`, string fields use `contains`
            # while numeric/bool fields use comparison operators.
            # @see: https://docs.vespa.ai/en/querying/query-language.html#map
            value = condition.value
            if isinstance(value, str):
                inner = f'key contains "{condition.key}", value contains "{value}"'
            else:
                inner = (
                    f'key contains "{condition.key}", value = {_format_value(value)}'
                )
            expr = f"{condition.field} contains sameElement({inner})"
            if condition.op == "not_eq":
                return f"!({expr})"
            return expr

        case LabelsCondition():
            value = condition.value
            labels_expr = f'labels.id contains "{value}"'
            concepts_expr = f'concepts.value contains "{value}"'
            if condition.op == "not_contains":
                return f"!({labels_expr} or {concepts_expr})"
            return f"({labels_expr} or {concepts_expr})"


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


# endregion Filters


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
            source = json.loads(fields.get("document_source"))
            if not source:
                logger.warning(f"Document source is missing for {hit.get("id")}")
                continue
            labels: list[LabelRelationship] = []
            for label in source.get("labels", []):
                labels.append(
                    LabelRelationship(
                        type=label.get("type", MISSING_PLACEHOLDER),
                        value=Label(
                            id=label.get("value").get("id", MISSING_PLACEHOLDER),
                            value=label.get("value").get("value", MISSING_PLACEHOLDER),
                            type=label.get("value").get("type", MISSING_PLACEHOLDER),
                        ),
                        timestamp=label.get("timestamp"),
                    )
                )

            for concept in fields.get("concepts", []):
                labels.append(
                    LabelRelationship(
                        type="concept",
                        value=Label(
                            id=concept.get("id", MISSING_PLACEHOLDER),
                            type="concept",
                            value=concept.get("value", MISSING_PLACEHOLDER),
                        ),
                        passages_id=concept.get("passages_id", MISSING_PLACEHOLDER),
                        count=concept.get("count", MISSING_PLACEHOLDER),
                    )
                )

            documents.append(
                Document(
                    id=source.get("id", MISSING_PLACEHOLDER),
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

    def search(self, query: str, label_type: str | None) -> list[Label]:
        """Fetch a list of relevant search results."""

        # 1) prefix filter the documents list on `labels_type_value_attribute` to ensure we are grouping by as few documents as possible for performance
        # We use `matches` with a case-insensitive regex pattern `(?i)` because `contains` on attributes is strictly case-sensitive.
        safe_terms = re.escape(query)
        safe_label_type = re.escape(label_type) if label_type else ""

        doc_regex = f"(?i)^{safe_label_type or "[^:]*"}::{safe_terms}.*"
        document_filter_query = f'select * from sources documents where labels_type_value_attribute matches "{doc_regex}"'

        # 2) group by all `labels_type_value_attribute` values that match the prefix
        grouping_query = "group(labels_type_value_attribute)"

        # 3) filter the group
        group_filter_query = (
            f'filter(regex("{doc_regex}", labels_type_value_attribute))'
        )
        # group_filter_query = ""

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
                if item.get("label") == "labels_type_value_attribute"
            ),
            [],
        )

        for group in group_list:
            label_type_value = group.get("value", "")
            label_type, _, label_value = label_type_value.partition("::")
            labels.append(
                Label(
                    id=label_type_value,
                    value=label_value,
                    type=label_type or MISSING_PLACEHOLDER,
                )
            )

        return labels

    def all_label_types(self) -> list[str]:
        """Fetch all distinct label types (unfiltered)."""
        yql = (
            "select * from sources documents where true "
            "| all(group(labels_type_attribute) "
            "order(-count()) each(output(count())))"
        )

        try:
            res = requests.post(
                f"{settings.vespa_endpoint}/search",
                json={
                    "yql": yql,
                    "hits": 0,
                    "timeout": "5s",
                },
                timeout=API_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {settings.vespa_read_token}",
                },
            )
        except Exception:
            logger.exception("Vespa all_label_types query failed")
            return []

        res = res.json()
        types: list[str] = []

        root = res.get("root", {})
        children = root.get("children", [{}])[0].get("children", [])
        group_list = next(
            (
                item.get("children", [])
                for item in children
                if item.get("label") == "labels_type_attribute"
            ),
            [],
        )

        for group in group_list:
            types.append(group.get("value", ""))

        return types

    def count(self, query: str) -> int:
        """Return hit count"""
        raise NotImplementedError()
