"""E2E facet tests — run against a real Vespa instance via the vespa_e2e fixtures."""

from typing import Any

from polyfactory.factories.typed_dict_factory import TypedDictFactory
from vespa.application import Vespa

from search.engines.dev_vespa import DevVespaDocumentSearchEngine, FieldFilter, Filter
from search.vespa.sources.data_in_api import (
    SourceDocument,
    SourceLabel,
    SourceLabelRelationship,
)
from tests.vespa_e2e import _TEST_SETTINGS, _feed_document

pytest_plugins = ["tests.vespa_e2e"]


class SourceLabelRelationshipFactory(TypedDictFactory):
    __model__ = SourceLabelRelationship

    @classmethod
    def build(cls, **kwargs: Any) -> SourceLabelRelationship:
        kwargs.setdefault("timestamp", None)
        return super().build(**kwargs)


class SourceDocumentFactory(TypedDictFactory):
    __model__ = SourceDocument

    @classmethod
    def build(cls, **kwargs: Any) -> SourceDocument:
        if "labels" not in kwargs:
            kwargs["labels"] = [SourceLabelRelationshipFactory.build()]
        if "documents" not in kwargs:
            kwargs["documents"] = []
        return super().build(**kwargs)


def _label(label_id: str, value: str, label_type: str) -> SourceLabelRelationship:
    return {
        "type": label_type,
        "value": SourceLabel(id=label_id, value=value, type=label_type),
        "timestamp": None,
    }


def _label_rel(label_id: str, value: str, label_type: str, relationship: str) -> SourceLabelRelationship:
    return {
        "type": relationship,
        "value": SourceLabel(id=label_id, value=value, type=label_type),
        "timestamp": None,
    }


def test_facets_no_filters_returns_counts_for_all_labels(vespa_app: Vespa):
    doc_law = SourceDocumentFactory.build(
        labels=[_label("category::Law", "Law", "category")],
    )
    doc_policy_1 = SourceDocumentFactory.build(
        labels=[_label("category::Policy", "Policy", "category")],
    )
    doc_policy_2 = SourceDocumentFactory.build(
        labels=[_label("category::Policy", "Policy", "category")],
    )
    _feed_document(vespa_app, doc_law)
    _feed_document(vespa_app, doc_policy_1)
    _feed_document(vespa_app, doc_policy_2)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_value_type_facets(query=None, filters_json_string=None)

    counts = {c.value.id: c.count for c in result["category"]}
    assert counts == {"category::Law": 1, "category::Policy": 2}


def test_facets_active_filter_keeps_all_options_in_that_group_visible(vespa_app: Vespa):
    doc_law_1 = SourceDocumentFactory.build(
        labels=[_label("category::Law", "Law", "category")],
    )
    doc_law_2 = SourceDocumentFactory.build(
        labels=[_label("category::Law", "Law", "category")],
    )
    doc_policy = SourceDocumentFactory.build(
        labels=[_label("category::Policy", "Policy", "category")],
    )
    _feed_document(vespa_app, doc_law_1)
    _feed_document(vespa_app, doc_law_2)
    _feed_document(vespa_app, doc_policy)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_value_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="contains", value="category::Law"
                )
            ],
        ).model_dump_json(),
    )

    counts = {c.value.id: c.count for c in result["category"]}
    assert counts == {"category::Law": 2, "category::Policy": 1}


def test_facets_active_filter_narrows_other_groups(vespa_app: Vespa):
    doc_law_usa = SourceDocumentFactory.build(
        labels=[
            _label("category::Law", "Law", "category"),
            _label("geography::USA", "USA", "geography"),
        ],
    )
    doc_law_gbr = SourceDocumentFactory.build(
        labels=[
            _label("category::Law", "Law", "category"),
            _label("geography::GBR", "GBR", "geography"),
        ],
    )
    doc_policy_aus = SourceDocumentFactory.build(
        labels=[
            _label("category::Policy", "Policy", "category"),
            _label("geography::AUS", "AUS", "geography"),
        ],
    )
    _feed_document(vespa_app, doc_law_usa)
    _feed_document(vespa_app, doc_law_gbr)
    _feed_document(vespa_app, doc_policy_aus)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_value_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="contains", value="category::Law"
                )
            ],
        ).model_dump_json(),
    )

    geography_counts = {c.value.id: c.count for c in result["geography"]}
    assert geography_counts == {"geography::USA": 1, "geography::GBR": 1}
    assert "geography::AUS" not in geography_counts


def test_facets_two_active_groups_drops_each_filter_independently(vespa_app: Vespa):
    # doc1: Law + USA, doc2: Policy + USA, doc3: Law + GBR
    doc_law_usa = SourceDocumentFactory.build(
        labels=[
            _label("category::Law", "Law", "category"),
            _label("geography::USA", "USA", "geography"),
        ],
    )
    doc_policy_usa = SourceDocumentFactory.build(
        labels=[
            _label("category::Policy", "Policy", "category"),
            _label("geography::USA", "USA", "geography"),
        ],
    )
    doc_law_gbr = SourceDocumentFactory.build(
        labels=[
            _label("category::Law", "Law", "category"),
            _label("geography::GBR", "GBR", "geography"),
        ],
    )
    _feed_document(vespa_app, doc_law_usa)
    _feed_document(vespa_app, doc_policy_usa)
    _feed_document(vespa_app, doc_law_gbr)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_value_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="contains", value="category::Law"
                ),
                FieldFilter(
                    field="labels.value.id", op="contains", value="geography::USA"
                ),
            ],
        ).model_dump_json(),
    )

    # `category` filter dropped with `geography::USA` still applied Law+USA and Policy+USA match
    category_counts = {c.value.id: c.count for c in result["category"]}
    assert category_counts == {"category::Law": 1, "category::Policy": 1}

    # `geography` filter dropped with `category::Law` still applied Law+USA and Law+GBR match
    geography_counts = {c.value.id: c.count for c in result["geography"]}
    assert geography_counts == {"geography::USA": 1, "geography::GBR": 1}


def test_facets_not_contains_filter_is_dropped_from_active_group(vespa_app: Vespa):
    doc_law_1 = SourceDocumentFactory.build(
        labels=[_label("category::Law", "Law", "category")],
    )
    doc_law_2 = SourceDocumentFactory.build(
        labels=[_label("category::Law", "Law", "category")],
    )
    doc_policy = SourceDocumentFactory.build(
        labels=[_label("category::Policy", "Policy", "category")],
    )
    _feed_document(vespa_app, doc_law_1)
    _feed_document(vespa_app, doc_law_2)
    _feed_document(vespa_app, doc_policy)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_value_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="not_contains", value="category::Policy"
                )
            ],
        ).model_dump_json(),
    )

    # `category` is active via `not_contains` so we drop the filter.
    # Policy thus appears despite being `not_contains`.
    counts = {c.value.id: c.count for c in result["category"]}
    assert counts == {"category::Law": 2, "category::Policy": 1}


def test_relationship_facets_no_filters_returns_counts_for_all_labels(vespa_app: Vespa):
    doc_law = SourceDocumentFactory.build(
        labels=[_label_rel("category::Law", "Law", "category", "part_of")],
    )
    doc_policy_1 = SourceDocumentFactory.build(
        labels=[_label_rel("category::Policy", "Policy", "category", "part_of")],
    )
    doc_policy_2 = SourceDocumentFactory.build(
        labels=[_label_rel("category::Policy", "Policy", "category", "part_of")],
    )
    _feed_document(vespa_app, doc_law)
    _feed_document(vespa_app, doc_policy_1)
    _feed_document(vespa_app, doc_policy_2)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_type_facets(query=None, filters_json_string=None)

    counts = {c.value.id: c.count for c in result["part_of"]}
    assert counts == {"category::Law": 1, "category::Policy": 2}


def test_relationship_facets_active_filter_narrows_the_group(vespa_app: Vespa):
    doc_law_1 = SourceDocumentFactory.build(
        labels=[_label_rel("category::Law", "Law", "category", "part_of")],
    )
    doc_law_2 = SourceDocumentFactory.build(
        labels=[_label_rel("category::Law", "Law", "category", "part_of")],
    )
    doc_policy = SourceDocumentFactory.build(
        labels=[_label_rel("category::Policy", "Policy", "category", "part_of")],
    )
    _feed_document(vespa_app, doc_law_1)
    _feed_document(vespa_app, doc_law_2)
    _feed_document(vespa_app, doc_policy)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="contains", value="category::Law"
                )
            ],
        ).model_dump_json(),
    )

    # The filter prefix ("category") does not match the facet group key ("part_of"),
    # so no disjunctive expansion occurs — the group is narrowed by the filter.
    counts = {c.value.id: c.count for c in result["part_of"]}
    assert counts == {"category::Law": 2}


def test_relationship_facets_active_filter_narrows_other_groups(vespa_app: Vespa):
    doc_law_gbr = SourceDocumentFactory.build(
        labels=[
            _label_rel("category::Law", "Law", "category", "part_of"),
            _label_rel("geography::GBR", "GBR", "geography", "submitted_to"),
        ],
    )
    doc_law_usa = SourceDocumentFactory.build(
        labels=[
            _label_rel("category::Law", "Law", "category", "part_of"),
            _label_rel("geography::USA", "USA", "geography", "submitted_to"),
        ],
    )
    doc_policy_aus = SourceDocumentFactory.build(
        labels=[
            _label_rel("category::Policy", "Policy", "category", "part_of"),
            _label_rel("geography::AUS", "AUS", "geography", "submitted_to"),
        ],
    )
    _feed_document(vespa_app, doc_law_gbr)
    _feed_document(vespa_app, doc_law_usa)
    _feed_document(vespa_app, doc_policy_aus)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="contains", value="category::Law"
                )
            ],
        ).model_dump_json(),
    )

    submitted_to_counts = {c.value.id: c.count for c in result["submitted_to"]}
    assert submitted_to_counts == {"geography::GBR": 1, "geography::USA": 1}
    assert "geography::AUS" not in submitted_to_counts


def test_relationship_facets_two_active_filters_narrow_all_groups(vespa_app: Vespa):
    # doc1: Law/part_of + GBR/submitted_to, doc2: Policy/part_of + GBR/submitted_to, doc3: Law/part_of + USA/submitted_to
    doc_law_gbr = SourceDocumentFactory.build(
        labels=[
            _label_rel("category::Law", "Law", "category", "part_of"),
            _label_rel("geography::GBR", "GBR", "geography", "submitted_to"),
        ],
    )
    doc_policy_gbr = SourceDocumentFactory.build(
        labels=[
            _label_rel("category::Policy", "Policy", "category", "part_of"),
            _label_rel("geography::GBR", "GBR", "geography", "submitted_to"),
        ],
    )
    doc_law_usa = SourceDocumentFactory.build(
        labels=[
            _label_rel("category::Law", "Law", "category", "part_of"),
            _label_rel("geography::USA", "USA", "geography", "submitted_to"),
        ],
    )
    _feed_document(vespa_app, doc_law_gbr)
    _feed_document(vespa_app, doc_policy_gbr)
    _feed_document(vespa_app, doc_law_usa)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="contains", value="category::Law"
                ),
                FieldFilter(
                    field="labels.value.id", op="contains", value="geography::GBR"
                ),
            ],
        ).model_dump_json(),
    )

    # Filter prefixes ("category", "geography") don't match relationship group keys,
    # so both filters apply to all groups — only doc1 matches both.
    part_of_counts = {c.value.id: c.count for c in result["part_of"]}
    assert part_of_counts == {"category::Law": 1}

    submitted_to_counts = {c.value.id: c.count for c in result["submitted_to"]}
    assert submitted_to_counts == {"geography::GBR": 1}


def test_relationship_facets_not_contains_filter_narrows_the_group(vespa_app: Vespa):
    doc_law_1 = SourceDocumentFactory.build(
        labels=[_label_rel("category::Law", "Law", "category", "part_of")],
    )
    doc_law_2 = SourceDocumentFactory.build(
        labels=[_label_rel("category::Law", "Law", "category", "part_of")],
    )
    doc_policy = SourceDocumentFactory.build(
        labels=[_label_rel("category::Policy", "Policy", "category", "part_of")],
    )
    _feed_document(vespa_app, doc_law_1)
    _feed_document(vespa_app, doc_law_2)
    _feed_document(vespa_app, doc_policy)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    result = engine.labels_type_facets(
        query=None,
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(
                    field="labels.value.id", op="not_contains", value="category::Policy"
                )
            ],
        ).model_dump_json(),
    )

    # The filter prefix ("category") does not match the facet group key ("part_of"),
    # so the not_contains filter is not dropped — Policy is excluded.
    counts = {c.value.id: c.count for c in result["part_of"]}
    assert counts == {"category::Law": 2}
