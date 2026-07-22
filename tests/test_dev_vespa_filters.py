"""Unit tests for Dev Vespa filter query construction."""

import pytest

from search.engines.dev_vespa import (
    AttributesCondition,
    Condition,
    FieldFilter,
    Filter,
    _build_condition_yql,
    _build_filter_yql,
    _facet_filter_label_type,
    _get_label_types_from_filters,
    _prune_filter,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)


def _documents_condition_yql(condition: Condition) -> str:
    """Build a single document condition's YQL with the document field map."""
    return _build_condition_yql(condition, documents_filter_field_to_vespa_field_map)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("document_id", "CCLW.doc.1.2", 'document_id contains "CCLW.doc.1.2"'),
        ("principal_id", "principal-1", 'principal_id contains "principal-1"'),
    ],
)
def test_passages_field_filter_builds_expected_yql(
    field: str, value: str, expected: str
) -> None:
    """Passage document/principal filters map to the native/imported attributes."""
    condition = FieldFilter(field=field, op="contains", value=value)
    assert (
        _build_condition_yql(condition, passages_filter_field_to_vespa_field_map)
        == expected
    )


def test_passages_filter_group_ands_document_and_principal() -> None: # trunk-ignore(typos)
    """A combined document+principal filter ANDs both conditions."""
    filter_group = Filter(
        op="and",
        filters=[
            FieldFilter(field="document_id", op="contains", value="doc-1"),
            FieldFilter(field="principal_id", op="contains", value="principal-1"),
        ],
    )
    assert _build_filter_yql(
        filter_group,
        passages_filter_field_to_vespa_field_map,
        passages_filter_struct_field_to_vespa_field_map,
    ) == ('(document_id contains "doc-1" and principal_id contains "principal-1")')


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
    assert (
        _documents_condition_yql(condition) == "attributes_published_date >= 1577836800"
    )


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
        _documents_condition_yql(condition)
        == "!(attributes_published_date = 1577836800)"
    )


def test_attributes_string_eq_uses_contains_same_element() -> None:
    """Ensure string attribute equality renders with sameElement contains checks."""
    condition = AttributesCondition(
        field="attributes_string",
        key="country",
        op="eq",
        value="UK",
    )
    assert _documents_condition_yql(condition) == (
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
    assert _documents_condition_yql(condition) == (
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
    assert _documents_condition_yql(condition) == (
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
    assert _documents_condition_yql(condition) == (
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
    assert _documents_condition_yql(condition) == (
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
    assert _documents_condition_yql(condition) == (
        'attributes_identifiers contains sameElement(key contains "project_id", '
        'value contains "proj-123")'
    )


def _labels_yql(filter_group: Filter) -> str:
    """Build YQL the way the labels engine does (struct map, empty field map)."""
    return _build_filter_yql(
        filter_group,
        field_map=labels_filter_field_to_vespa_field_map,
        struct_map=labels_filter_struct_field_to_vespa_field_map,
    )


def test_labels_field_filter_expands_to_labels_and_concepts() -> None:
    """Ensure mapped label field generates a two-field OR expression."""
    condition = FieldFilter(
        field="labels.value.value",
        op="contains",
        value="Romania",
    )
    assert _documents_condition_yql(condition) == (
        '(labels.value contains "Romania" or concepts.value contains "Romania")'
    )


def test_labels_not_contains_wraps_mapped_or_expression() -> None:
    """Ensure not_contains negates the expanded OR expression."""
    condition = FieldFilter(
        field="labels.value.value",
        op="not_contains",
        value="Romania",
    )
    assert _documents_condition_yql(condition) == (
        '!(labels.value contains "Romania" or concepts.value contains "Romania")'
    )


def test_labels_struct_map_groups_and_conditions_into_same_element() -> None:
    """An AND group of struct fields renders one ``sameElement`` (same element)."""
    filter_group = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.type", op="contains", value="subconcept_of"),
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="category::UN Submission",
            ),
        ],
    )
    assert _labels_yql(filter_group) == (
        'labels contains sameElement(relationship contains "subconcept_of", '
        'id contains "category::UN Submission")'
    )


def test_labels_struct_map_or_conditions_use_separate_same_elements() -> None:
    """An OR group renders one ``sameElement`` per condition (different elements)."""
    filter_group = Filter(
        op="or",
        filters=[
            FieldFilter(field="labels.value.id", op="contains", value="a"),
            FieldFilter(field="labels.value.id", op="contains", value="b"),
        ],
    )
    assert _labels_yql(filter_group) == (
        '(labels contains sameElement(id contains "a") '
        'or labels contains sameElement(id contains "b"))'
    )


def test_labels_struct_map_not_contains_negates_same_element() -> None:
    """A ``not_contains`` struct condition wraps its own ``sameElement``."""
    filter_group = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.type", op="not_contains", value="related_to"),
        ],
    )
    assert _labels_yql(filter_group) == (
        '!(labels contains sameElement(relationship contains "related_to"))'
    )


def test_labels_struct_map_mixes_struct_and_top_level_fields() -> None:
    """Non-struct fields fall through to ``_build_condition_yql`` unchanged."""
    filter_group = Filter(
        op="and",
        filters=[
            FieldFilter(field="type", op="not_contains", value="category"),
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="category::UN Submission",
            ),
        ],
    )
    assert _labels_yql(filter_group) == (
        '(!(type contains "category") '
        'and labels contains sameElement(id contains "category::UN Submission"))'
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

    assert _build_filter_yql(
        filter_group,
        field_map=documents_filter_field_to_vespa_field_map,
        struct_map=documents_filter_struct_field_to_vespa_field_map,
    ) == (
        '(((labels.value contains "UN" or concepts.value contains "UN") or '
        '(labels.value contains "Romania" or concepts.value contains "Romania")) and '
        'attributes_double contains sameElement(key contains "project_cost_usd", '
        "value > 100.0))"
    )


# region Faceting helpers


def test_facet_filter_label_type_extracts_prefix_from_id_value() -> None:
    """`labels.value.id` filters carry the type as a prefix on their value."""
    condition = FieldFilter(
        field="labels.value.id",
        op="contains",
        value="category::Law",
    )
    assert _facet_filter_label_type(condition) == "category"


def test_facet_filter_label_type_returns_none_for_value_filter() -> None:
    """Value-based label filters carry no type prefix and return None."""
    condition = FieldFilter(
        field="labels.value.value",
        op="contains",
        value="Romania",
    )
    assert _facet_filter_label_type(condition) is None


def test_facet_filter_label_type_returns_none_for_attribute_condition() -> None:
    """Attribute conditions are never typed-facet selections."""
    condition = AttributesCondition(
        field="attributes_double",
        key="project_cost_usd",
        op="eq",
        value=1.0,
    )
    assert _facet_filter_label_type(condition) is None


def test_get_label_types_from_filters_walks_nested_groups() -> None:
    """All typed selections in a nested tree are collected."""
    tree = Filter(
        op="and",
        filters=[
            Filter(
                op="or",
                filters=[
                    FieldFilter(
                        field="labels.value.id",
                        op="contains",
                        value="category::Law",
                    ),
                    FieldFilter(
                        field="labels.value.id",
                        op="contains",
                        value="category::Policy",
                    ),
                ],
            ),
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="geography::USA",
            ),
            FieldFilter(
                field="labels.value.value",
                op="contains",
                value="Romania",
            ),
        ],
    )
    assert _get_label_types_from_filters(tree) == {"category", "geography"}


def test_prune_filter_drops_matching_conditions_and_collapses_empty_groups() -> None:
    """Pruning removes hits and collapses groups that become empty."""
    tree = Filter(
        op="and",
        filters=[
            Filter(
                op="or",
                filters=[
                    FieldFilter(
                        field="labels.value.id",
                        op="contains",
                        value="category::Law",
                    ),
                    FieldFilter(
                        field="labels.value.id",
                        op="contains",
                        value="category::Policy",
                    ),
                ],
            ),
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="geography::USA",
            ),
        ],
    )
    pruned = _prune_filter(tree, lambda c: _facet_filter_label_type(c) == "category")
    assert pruned == Filter(
        op="and",
        filters=[
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="geography::USA",
            ),
        ],
    )


def test_prune_filter_collapses_to_none_when_everything_drops() -> None:
    """A tree where every leaf is dropped collapses to None."""
    tree = Filter(
        op="and",
        filters=[
            FieldFilter(
                field="labels.value.id",
                op="contains",
                value="category::Law",
            ),
        ],
    )
    assert _prune_filter(tree, lambda _c: True) is None


# endregion
