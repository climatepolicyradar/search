"""Unit tests for Dev Vespa filter query construction."""

import pytest

from search.engines.dev_vespa import (
    AttributesCondition,
    FieldFilter,
    Filter,
    _build_condition_yql,
    _build_filter_yql,
)


def test_published_date_filter_targets_scalar_vespa_field() -> None:
    """
    Ensure published-date comparisons use ``attributes_published_date``.

    :return: ``None``.
    :rtype: None
    """
    condition = AttributesCondition(
        field="attributes.published_date",
        key="published_date",
        op="gte",
        value="2020-01-01T00:00:00Z",
    )
    assert _build_condition_yql(condition) == "attributes_published_date >= 1577836800"


def test_published_date_not_eq_uses_negated_scalar_field() -> None:
    """
    Ensure published-date ``not_eq`` uses the scalar field and negation.

    :return: ``None``.
    :rtype: None
    """
    condition = AttributesCondition(
        field="attributes.published_date",
        key="published_date",
        op="not_eq",
        value="2020-01-01T00:00:00Z",
    )
    assert (
        _build_condition_yql(condition) == "!(attributes_published_date = 1577836800)"
    )


def test_attributes_string_eq_uses_contains_same_element() -> None:
    """Ensure string attribute equality renders with sameElement contains checks."""
    condition = AttributesCondition(
        field="attributes_string",
        key="country",
        op="eq",
        value="UK",
    )
    assert _build_condition_yql(condition) == (
        'attributes_string contains sameElement(key contains "country", '
        'value contains "UK")'
    )


def test_attributes_string_not_eq_wraps_negation() -> None:
    """Ensure string attribute not-equals wraps equality expression in negation."""
    condition = AttributesCondition(
        field="attributes_string",
        key="country",
        op="not_eq",
        value="UK",
    )
    assert _build_condition_yql(condition) == (
        '!(attributes_string contains sameElement(key contains "country", '
        'value contains "UK"))'
    )


@pytest.mark.parametrize(
    ("op", "expected_symbol"),
    [("eq", "="), ("lt", "<"), ("lte", "<="), ("gt", ">"), ("gte", ">=")],
)
def test_attributes_double_numeric_ops_render_expected_symbol(
    op: str, expected_symbol: str
) -> None:
    """Ensure numeric attributes map each operator to the expected symbol."""
    condition = AttributesCondition(
        field="attributes_double",
        key="project_cost_usd",
        op=op,  # type: ignore[arg-type]
        value=1_000_000.0,
    )
    assert _build_condition_yql(condition) == (
        "attributes_double contains "
        f'sameElement(key contains "project_cost_usd", value {expected_symbol} 1000000.0)'
    )


def test_attributes_double_not_eq_wraps_eq_expression() -> None:
    """Ensure numeric not-equals reuses equality then wraps with negation."""
    condition = AttributesCondition(
        field="attributes_double",
        key="project_cost_usd",
        op="not_eq",
        value=1_000_000.0,
    )
    assert _build_condition_yql(condition) == (
        "!(attributes_double contains "
        'sameElement(key contains "project_cost_usd", value = 1000000.0))'
    )


def test_attributes_boolean_eq_renders_as_byte_value() -> None:
    """Ensure boolean values map to Vespa byte-compatible representation."""
    condition = AttributesCondition(
        field="attributes_boolean",
        key="is_active",
        op="eq",
        value=True,
    )
    assert _build_condition_yql(condition) == (
        'attributes_boolean contains sameElement(key contains "is_active", value = 1)'
    )


def test_attributes_identifiers_eq_renders_string_contains() -> None:
    """Ensure identifier attributes use string contains semantics."""
    condition = AttributesCondition(
        field="attributes_identifiers",
        key="project_id",
        op="eq",
        value="proj-123",
    )
    assert _build_condition_yql(condition) == (
        'attributes_identifiers contains sameElement(key contains "project_id", '
        'value contains "proj-123")'
    )


def test_labels_field_filter_expands_to_labels_and_concepts() -> None:
    """Ensure mapped label field generates a two-field OR expression."""
    condition = FieldFilter(
        field="labels.value.value",
        op="contains",
        value="Romania",
    )
    assert _build_condition_yql(condition) == (
        '(labels.value contains "Romania" or concepts.value contains "Romania")'
    )


def test_labels_not_contains_wraps_mapped_or_expression() -> None:
    """Ensure not_contains negates the expanded OR expression."""
    condition = FieldFilter(
        field="labels.value.value",
        op="not_contains",
        value="Romania",
    )
    assert _build_condition_yql(condition) == (
        '!(labels.value contains "Romania" or concepts.value contains "Romania")'
    )


def test_nested_filter_group_renders_with_parentheses() -> None:
    """Ensure nested AND/OR groups preserve logical grouping in YQL output."""
    filter_group = Filter(
        op="and",
        filters=[
            Filter(
                op="or",
                filters=[
                    FieldFilter(
                        field="labels.value.value",
                        op="contains",
                        value="UN",
                    ),
                    FieldFilter(
                        field="labels.value.value",
                        op="contains",
                        value="Romania",
                    ),
                ],
            ),
            AttributesCondition(
                field="attributes_double",
                key="project_cost_usd",
                op="gt",
                value=100.0,
            ),
        ],
    )
    assert _build_filter_yql(filter_group) == (
        '(((labels.value contains "UN" or concepts.value contains "UN") or '
        '(labels.value contains "Romania" or concepts.value contains "Romania")) and '
        'attributes_double contains sameElement(key contains "project_cost_usd", '
        "value > 100.0))"
    )
