"""Filter model and YQL-building for Vespa queries."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel

from search.engines.vespa_query.sorting import sort_field_to_vespa_field_map


class AttributesCondition(BaseModel):
    field: Literal[
        "attributes_string",
        "attributes_double",
        "attributes_boolean",
        "attributes_identifiers",
        "attributes.published_date",
    ]
    key: str
    op: Literal["eq", "not_eq", "lt", "lte", "gt", "gte"]
    value: str | int | float | bool


class FieldFilter(BaseModel):
    field: str
    op: Literal["contains", "not_contains"]
    value: str | float | bool


Condition = AttributesCondition | FieldFilter


class Filter(BaseModel):
    """A group of filters combined with AND or OR. Supports arbitrary nesting."""

    op: Literal["and", "or"]
    filters: list[Condition | Filter]


TOPIC_ID_PREFIX = "concept::"
TOPIC_FILTER_FIELD = "labels.value.id"


def normalise_topic_id(topic: str) -> str:
    """Give a bare wikibase id the `concept::` prefix stored in `concepts.id`."""
    return topic if topic.startswith(TOPIC_ID_PREFIX) else f"{TOPIC_ID_PREFIX}{topic}"


def _topic_ids_from_filters(filter_group: Filter | None) -> list[str]:
    """
    The topic ids a filter tree selects for, in order and deduplicated.

    `not_contains` conditions are skipped: excluding a topic must not boost it.
    """
    if filter_group is None:
        return []
    topic_ids: dict[str, None] = {}
    for item in filter_group.filters:
        if isinstance(item, Filter):
            topic_ids.update(dict.fromkeys(_topic_ids_from_filters(item)))
        elif (
            isinstance(item, FieldFilter)
            and item.field == TOPIC_FILTER_FIELD
            and item.op == "contains"
            and isinstance(item.value, str)
            and item.value.startswith(TOPIC_ID_PREFIX)
        ):
            topic_ids[item.value] = None
    return list(topic_ids)


class ArrayStructField(NamedTuple):
    """Used to locate a subfield within a Vespa array-of-structs field."""

    array_field: str
    subfield: str


# Simple example: label contains "Romania"
SimpleExampleFilter = Filter(
    op="and",
    filters=[
        FieldFilter(
            field="labels.value.value",
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
                        FieldFilter(
                            field="labels.value.value",
                            op="contains",
                            value="Multilateral climate fund project",
                        ),
                        FieldFilter(
                            field="labels.value.value",
                            op="contains",
                            value="Principal",
                        ),
                    ],
                ),
                FieldFilter(
                    field="labels.value.value",
                    op="contains",
                    value="UN submissions",
                ),
            ],
        ),
        FieldFilter(
            field="labels.value.value",
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


def _format_value(value: str | int | float | bool) -> str:
    """Format a value for YQL: strings get quotes, numbers do not, bools become 1/0 (byte)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'


def _to_unix_timestamp(value: str) -> int:
    """Convert an ISO datetime string to Unix timestamp (seconds)."""
    normalised = value.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalised).timestamp())


def _published_date_operand(value: str | int | float, op: str) -> int:
    """
    Translate a published-date filter value into epoch seconds.

    ``attributes.published_date`` is stored as a scalar Unix timestamp in
    Vespa. The API normalises ISO datetime strings at the boundary, and we keep
    this fallback conversion here to preserve existing callers.
    """
    _ = op
    if isinstance(value, str):
        return _to_unix_timestamp(value)
    return int(value)


_value_type_to_vespa_attributes_field = {
    str: "attributes_string",
    float: "attributes_double",
    int: "attributes_double",
    bool: "attributes_boolean",
}


def _build_condition_yql(
    condition: Condition,
    field_map: dict[str, list[str]],
) -> str:
    match condition:
        case AttributesCondition():
            if condition.field == "attributes.published_date":
                vespa_field = sort_field_to_vespa_field_map.get(
                    condition.field, [condition.field]
                )[0]
                op_to_symbol = {
                    "eq": "=",
                    "lt": "<",
                    "lte": "<=",
                    "gt": ">",
                    "gte": ">=",
                }
                operand = _published_date_operand(condition.value, condition.op)
                if condition.op == "not_eq":
                    return f"!({vespa_field} = {operand})"
                op_symbol = op_to_symbol.get(condition.op)
                if op_symbol is None:
                    raise ValueError(
                        f"unsupported op={condition.op!r} for field={condition.field!r}"
                    )
                return f"{vespa_field} {op_symbol} {operand}"

            # Using `sameElement`, string fields use `contains`
            # while numeric/bool fields use comparison operators.
            # @see: https://docs.vespa.ai/en/querying/query-language.html#map
            value = condition.value
            if isinstance(value, str):
                if condition.op not in ("eq", "not_eq"):
                    raise ValueError(
                        f"string attributes only support eq/not_eq, got {condition.op!r}"
                    )
                inner = f'key contains "{condition.key}", value contains "{value}"'
            else:
                op_to_symbol = {
                    "eq": "=",
                    "not_eq": "=",
                    "lt": "<",
                    "lte": "<=",
                    "gt": ">",
                    "gte": ">=",
                }
                op_symbol = op_to_symbol.get(condition.op)
                if op_symbol is None:
                    raise ValueError(
                        f"unsupported op={condition.op!r} for field={condition.field!r}"
                    )
                inner = f'key contains "{condition.key}", value {op_symbol} {_format_value(value)}'
            expr = f"{condition.field} contains sameElement({inner})"
            if condition.op == "not_eq":
                return f"!({expr})"
            return expr

        case FieldFilter() if condition.field.startswith("attributes."):
            key = condition.field.split(".", 1)[1]
            vespa_field = _value_type_to_vespa_attributes_field[type(condition.value)]
            # we need to use `contains` on strings
            if isinstance(condition.value, str):
                inner = f'key contains "{key}", value contains "{condition.value}"'
            # and operators e.g. `=` on numerics & bools
            else:
                inner = (
                    f'key contains "{key}", value = {_format_value(condition.value)}'
                )
            expr = f"{vespa_field} contains sameElement({inner})"
            if condition.op == "not_contains":
                return f"!({expr})"
            return expr

        case FieldFilter():
            fields = field_map.get(condition.field, [condition.field])
            value = _format_value(condition.value)
            exprs = [f"{field} contains {value}" for field in fields]
            combined = " or ".join(exprs)
            if condition.op == "not_contains":
                return f"!({combined})"
            return f"({combined})" if len(exprs) > 1 else combined


def _build_filter_yql(
    filter_group: Filter,
    field_map: dict[str, list[str]],
    struct_map: dict[str, ArrayStructField],
) -> str:
    """Recursively build YQL for a filter group"""
    parts: list[str] = []
    # `contains` conditions grouped by struct to allow us to filter on more than 1 field of a struct.
    struct_operands: dict[str, list[str]] = {}

    for item in filter_group.filters:
        if isinstance(item, Filter):
            parts.append(_build_filter_yql(item, field_map, struct_map))
        elif isinstance(item, FieldFilter) and item.field in struct_map:
            struct = struct_map[item.field]
            operand = f"{struct.subfield} contains {_format_value(item.value)}"
            if item.op == "not_contains":
                parts.append(f"!({struct.array_field} contains sameElement({operand}))")
            else:
                struct_operands.setdefault(struct.array_field, []).append(operand)
        else:
            parts.append(_build_condition_yql(item, field_map))

    for array_field, operands in struct_operands.items():
        if filter_group.op == "and":
            # All conditions must match the same element.
            parts.append(f"{array_field} contains sameElement({', '.join(operands)})")
        else:
            # OR: each condition may match a different element.
            parts.extend(
                f"{array_field} contains sameElement({operand})" for operand in operands
            )

    if not parts:
        return ""

    joined = f" {filter_group.op} ".join(parts)

    # Wrap in parentheses if multiple parts
    return f"({joined})" if len(parts) > 1 else joined


def _build_filter_query(
    filter_group: Filter | None,
    field_map: dict[str, list[str]],
    struct_map: dict[str, ArrayStructField],
) -> str:
    """Build the WHERE clause from a filter group."""
    if filter_group is None:
        return ""
    yql = _build_filter_yql(filter_group, field_map, struct_map)
    return f" and {yql}" if yql else ""


def _facet_filter_label_type(condition: Condition) -> str | None:
    """Returns the label.type parsed label.id"""
    if (
        isinstance(condition, FieldFilter)
        and condition.field in ("labels.value.id", "concepts.value.id")
        and isinstance(condition.value, str)
    ):
        prefix, sep, _ = condition.value.partition("::")
        return prefix if sep else None
    if (
        isinstance(condition, FieldFilter)
        and condition.field == "labels.type"
        and isinstance(condition.value, str)
    ):
        return condition.value
    return None


def _prune_filter(
    filter_group: Filter | None,
    filter_method: Callable[[Condition], bool],
) -> Filter | None:
    """Return a copy of `filter_group` with a filter_method applied"""
    if filter_group is None:
        return None
    new_filters: list[Condition | Filter] = []
    for item in filter_group.filters:
        if isinstance(item, Filter):
            pruned = _prune_filter(item, filter_method)
            if pruned is not None:
                new_filters.append(pruned)
        elif not filter_method(item):
            new_filters.append(item)
    if not new_filters:
        return None
    return Filter(op=filter_group.op, filters=new_filters)


def _get_label_types_from_filters(filter_group: Filter | None) -> set[str]:
    """Returns a set of `labels.types` recursively from the `filter_group`"""
    if filter_group is None:
        return set()

    label_types: set[str] = set()
    for filter_item in filter_group.filters:
        # If this is a `Filter`, recurse
        if isinstance(filter_item, Filter):
            label_types |= _get_label_types_from_filters(filter_item)
        # Otherwise get the `label_type` from the condition
        else:
            label_type = _facet_filter_label_type(filter_item)
            if label_type is not None:
                label_types.add(label_type)

    return label_types
