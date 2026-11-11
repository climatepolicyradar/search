from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from api.geographies_taxonomy import geographies_taxonomy
from api.labels_taxonomy import labels_taxonomy
from api.mcp.filters import (
    Category,
    FilterArgError,
    Region,
    ResponseArea,
    build_filter,
)
from search.engines.dev_vespa import AttributesCondition, FieldFilter, Filter


def label_ids(group: Filter) -> list[str | float | bool]:
    return [
        condition.value
        for condition in group.filters
        if isinstance(condition, FieldFilter)
    ]


TAXONOMY_TYPES = [
    (Category, labels_taxonomy, "category"),
    (ResponseArea, labels_taxonomy, "topic"),
    (Region, geographies_taxonomy, "region"),
]


@pytest.mark.parametrize(("arg_type", "taxonomy", "label_type"), TAXONOMY_TYPES)
def test_schema_lists_every_taxonomy_value(
    arg_type: Any, taxonomy: list, label_type: str
):
    # The model only sees the choices through the schema.
    expected = [label.value for label in taxonomy if label.type == label_type]

    assert TypeAdapter(arg_type).json_schema()["enum"] == expected
    assert TypeAdapter(arg_type).validate_python(expected[0]) == expected[0]


@pytest.mark.parametrize("arg_type", [Category, ResponseArea, Region])
def test_value_outside_the_taxonomy_is_rejected(arg_type: Any):
    with pytest.raises(ValidationError):
        TypeAdapter(arg_type).validate_python("Atlantis")


def test_no_args_is_no_filter():
    assert build_filter() is None


def test_empty_lists_are_no_filter():
    assert build_filter(geographies=[], categories=[]) is None


def test_geographies_are_ored_label_ids():
    tree = build_filter(geographies=["KEN", " gbr "])

    assert tree is not None
    assert tree.op == "and"
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert group.op == "or"
    # Countries are indexed as `country::`, not `geography::`.
    assert label_ids(group) == ["country::KEN", "country::GBR"]


def test_categories_are_ored_label_ids():
    tree = build_filter(categories=["Law", "UN submission"])

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert label_ids(group) == ["category::Law", "category::UN submission"]


def test_response_areas_are_ored_label_ids():
    tree = build_filter(response_areas=["Adaptation", "Loss and damage"])

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert label_ids(group) == ["topic::Adaptation", "topic::Loss and damage"]


def test_dates_cover_whole_days_as_epoch_seconds():
    tree = build_filter(
        published_after=date(2020, 1, 1), published_before=date(2020, 12, 31)
    )

    assert tree is not None
    after, before = tree.filters
    assert isinstance(after, AttributesCondition)
    assert isinstance(before, AttributesCondition)
    assert (after.field, after.key, after.op) == (
        "attributes.published_date",
        "published_date",
        "gte",
    )
    assert after.value == int(datetime(2020, 1, 1, tzinfo=UTC).timestamp())
    assert before.op == "lte"
    assert before.value == int(
        datetime(2020, 12, 31, 23, 59, 59, tzinfo=UTC).timestamp()
    )


def test_groups_are_anded():
    tree = build_filter(
        geographies=["KEN"], categories=["Law"], published_after=date(2020, 1, 1)
    )

    assert tree is not None
    assert tree.op == "and"
    assert len(tree.filters) == 3


def test_topics_take_bare_or_prefixed_ids():
    tree = build_filter(topics=["Q1343", "concept::Q7987"])

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert label_ids(group) == ["concept::Q1343", "concept::Q7987"]


def test_topic_name_points_to_search_topics():
    with pytest.raises(FilterArgError, match="search_topics"):
        build_filter(topics=["adaptation finance"])


def test_country_name_asks_for_iso3():
    with pytest.raises(FilterArgError, match="'KEN'"):
        build_filter(geographies=["Kenya"])


def test_unknown_iso3_code_is_rejected_not_silently_empty():
    with pytest.raises(FilterArgError, match="isn't a country code we have"):
        build_filter(geographies=["ZZZ"])


def test_principals_only_adds_the_principal_label():
    tree = build_filter(principals_only=True)

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert label_ids(group) == ["status::Principal"]


def test_regions_are_ored_region_label_ids():
    tree = build_filter(regions=["Sub-Saharan Africa", "South Asia"])

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert label_ids(group) == ["region::SSF", "region::SAS"]


def test_passages_match_document_labels_on_their_document():
    tree = build_filter(
        geographies=["KEN"],
        regions=["Sub-Saharan Africa"],
        categories=["Law"],
        for_passages=True,
    )

    assert tree is not None
    assert [
        (condition.field, condition.value)
        for group in tree.filters
        if isinstance(group, Filter)
        for condition in group.filters
        if isinstance(condition, FieldFilter)
    ] == [
        ("labels_type_id_value_attribute", "country::country::KEN::Kenya"),
        ("labels_type_id_value_attribute", "region::region::SSF::Sub-Saharan Africa"),
        ("labels_type_id_value_attribute", "category::category::Law::Law"),
    ]


def test_passages_match_topics_on_their_own_labels():
    tree = build_filter(topics=["Q1343"], for_passages=True)

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    (condition,) = group.filters
    assert isinstance(condition, FieldFilter)
    assert (condition.field, condition.value) == ("labels.value.id", "concept::Q1343")


def test_impossible_date_range_is_rejected_not_silently_empty():
    with pytest.raises(FilterArgError, match="later than published_before"):
        build_filter(
            published_after=date(2024, 1, 1), published_before=date(2020, 1, 1)
        )


def test_a_single_day_range_is_allowed():
    assert (
        build_filter(
            published_after=date(2024, 1, 1), published_before=date(2024, 1, 1)
        )
        is not None
    )


def test_accented_country_names_match_on_passages():
    # The exact match includes the name, so accents and apostrophes must
    # come through as stored.
    tree = build_filter(geographies=["CIV"], for_passages=True)

    assert tree is not None
    (group,) = tree.filters
    assert isinstance(group, Filter)
    assert label_ids(group) == ["country::country::CIV::Côte d'Ivoire"]
