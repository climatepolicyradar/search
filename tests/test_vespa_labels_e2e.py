"""
Labels e2e tests for Vespa.

E2E tests for labels: document-embedded label filters, concepts via the
label filter surface, label linguistics, and the standalone ``labels`` schema.

Run against a real Vespa instance via the shared ``vespa_e2e`` fixtures
(port 8089). Run with: uv run pytest tests/test_vespa_labels_e2e.py
"""

from typing import Any
from urllib.parse import quote

import pytest
import requests as req
from cpr_contracts import (
    Document,
    DocumentLabelRelationship,
    Label,
)
from polyfactory.factories.pydantic_factory import ModelFactory
from vespa.application import Vespa

from search.data_in_models import Label as DataInLabel
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    FieldFilter,
    Filter,
)
from search.vespa.documents_feed_materializer import _source_document_to_vespa_update
from search.vespa.labels_feed_materializer import (
    VespaLabel,
    VespaLabelLabelRelationship,
    _vespa_label_to_vespa_update,
)
from tests.vespa_e2e import _TEST_SETTINGS, get_search_ids

pytest_plugins = ["tests.vespa_e2e"]


class DocumentLabelRelationshipFactory(ModelFactory[DocumentLabelRelationship]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> DocumentLabelRelationship:
        kwargs.setdefault("timestamp", None)
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


class DocumentFactory(ModelFactory[Document]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> Document:
        if "labels" not in kwargs:
            kwargs["labels"] = [DocumentLabelRelationshipFactory.build()]
        if "documents" not in kwargs:
            kwargs["documents"] = []
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


def _make_label(label_id: str) -> DocumentLabelRelationship:
    return DocumentLabelRelationship(
        type="entity_type",
        value=Label(id=label_id, value=label_id, type="entity_type", labels=[]),
        timestamp=None,
    )


def _label_source_from_taxonomy(label_id: str, label_type: str, value: str) -> str:
    """Serialise a taxonomy/concept label (see labels_feed_materializer)."""
    return DataInLabel(id=label_id, type=label_type, value=value).model_dump_json()


def _taxonomy_vespa_label(
    label_id: str,
    label_type: str,
    value: str,
    labels: list[VespaLabelLabelRelationship] | None = None,
) -> VespaLabel:
    """Build a ``VespaLabel`` for direct feed to the labels schema in e2e tests."""
    return VespaLabel(
        id=label_id,
        type=label_type,
        value=value,
        alternative_labels=[],
        subconcept_labels=[],
        description="",
        negative_labels=[],
        labels=labels or [],
        label_source=_label_source_from_taxonomy(label_id, label_type, value),
    )


def _relationship(parent_id: str, relationship: str) -> VespaLabelLabelRelationship:
    """Build a nested ``labels`` struct entry (a taxonomy relationship)."""
    return {
        "id": parent_id,
        "type": "category",
        "value": parent_id.split("::", 1)[-1],
        "timestamp": None,
        "relationship": relationship,
    }


def _feed_document(app: Vespa, document: Document) -> None:
    op = _source_document_to_vespa_update(document)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={**op, "create": True},  # type: ignore[arg-type]
        timeout=5,
    )
    r.raise_for_status()


def _feed_concepts(
    app: Vespa, document: Document, concept_id: str, concept_name: str
) -> None:
    """Update an existing document with a single concept."""
    vespa_concepts = [
        {
            "id": concept_id,
            "type": "concept",
            "value": concept_name,
            "count": 1,
            "passages_id": "test",
        }
    ]

    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={"fields": {"concepts": {"assign": vespa_concepts}}},
        timeout=5,
    )
    r.raise_for_status()


def _flatten_tokens(token_field: Any) -> list[str]:
    """
    Flatten Vespa token summary output into a list of strings.

    Lucene linguistics with ``stemming: multiple`` returns each token as
    either a plain string or a list of stems (e.g. ``["run", "running"]``).
    This helper normalises both shapes into a flat list.
    """
    if isinstance(token_field, dict):
        items = token_field.get("values", [])
    elif isinstance(token_field, list):
        items = token_field
    else:
        return []
    flat: list[str] = []
    for item in items:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


def _feed_label(vespa_app: Vespa, vespa_label: VespaLabel) -> None:
    vespa_update = _vespa_label_to_vespa_update(vespa_label)
    response = req.put(
        f"{vespa_app.end_point}/document/v1/labels/labels/docid/{quote(vespa_update['update'], safe='')}?create=true",
        json={"fields": vespa_update["fields"]},  # type: ignore[arg-type]
        timeout=5,
    )
    if not response.ok:
        print(f"Feed label error {response.status_code}: {response.text}")
    response.raise_for_status()


@pytest.fixture(autouse=True)
def clean_labels(vespa_app: Vespa):
    yield
    vespa_app.delete_all_docs(content_cluster_name="search-production", schema="labels")


# region Document label filters


def test_labels_contains_returns_matching_doc(vespa_app: Vespa):
    doc_with_label = DocumentFactory.build(labels=[_make_label("Romania")])
    doc_without_label = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_label.id in ids
    assert doc_without_label.id not in ids


def test_labels_contains_excludes_non_matching_doc(vespa_app: Vespa):
    doc_with_different_label = DocumentFactory.build(
        labels=[_make_label("France")]
    )
    doc_without_label = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_different_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_different_label.id not in ids
    assert doc_without_label.id not in ids


def test_labels_not_contains_excludes_matching_doc(vespa_app: Vespa):
    doc_with_label = DocumentFactory.build(labels=[_make_label("Romania")])
    doc_without_label = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="not_contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_label.id not in ids
    assert doc_without_label.id in ids


def test_labels_not_contains_returns_non_matching_doc(vespa_app: Vespa):
    doc_with_different_label = DocumentFactory.build(
        labels=[_make_label("France")]
    )
    doc_with_matching_label = DocumentFactory.build(
        labels=[_make_label("Romania")]
    )
    _feed_document(vespa_app, doc_with_different_label)
    _feed_document(vespa_app, doc_with_matching_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="not_contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_different_label.id in ids
    assert doc_with_matching_label.id not in ids


# endregion Document label filters

# region Concepts via label filter


def test_concepts_contains_returns_matching_doc(vespa_app: Vespa):
    doc_with_concept = DocumentFactory.build(labels=[])
    doc_without_concept = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_concept, "Romania", "Romania")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_concept.id in ids
    assert doc_without_concept.id not in ids


def test_concepts_contains_excludes_non_matching_doc(vespa_app: Vespa):
    doc_with_different_concept = DocumentFactory.build(labels=[])
    doc_without_concept = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_different_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_different_concept, "France", "France")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_different_concept.id not in ids
    assert doc_without_concept.id not in ids


def test_concepts_not_contains_excludes_matching_doc(vespa_app: Vespa):
    doc_with_concept = DocumentFactory.build(labels=[])
    doc_without_concept = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_concept, "Romania", "Romania")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="not_contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_concept.id not in ids
    assert doc_without_concept.id in ids


def test_concepts_not_contains_returns_non_matching_doc(vespa_app: Vespa):
    doc_with_different_concept = DocumentFactory.build(labels=[])
    doc_with_matching_concept = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_different_concept)
    _feed_document(vespa_app, doc_with_matching_concept)
    _feed_concepts(vespa_app, doc_with_different_concept, "France", "France")
    _feed_concepts(vespa_app, doc_with_matching_concept, "Romania", "Romania")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="not_contains", value="Romania")
        ],
    )
    ids = get_search_ids(f)
    assert doc_with_different_concept.id in ids
    assert doc_with_matching_concept.id not in ids


# endregion Concepts via label filter

# region Label linguistics


def test_linguistics_label_tokens_are_not_stemmed(vespa_app: Vespa):
    """
    Labels use label_analysis profile: lowercase only, no stemming.

    "Running" should become "running" (not "run").
    Search by title so userQuery() matches via the default fieldset.
    """
    doc = DocumentFactory.build(
        title="Running Waters document",
        description="Test description",
        labels=[
            DocumentLabelRelationship(
                type="topic",
                value=Label(id="running-waters", value="Running Waters", type="topic", labels=[]),
                timestamp=None,
            )
        ],
    )
    _feed_document(vespa_app, doc)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS, debug=True)
    results = engine.search(
        query="running",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
    ).results
    assert len(results) >= 1, f"Expected results, got: {results}"

    debug = engine.last_debug_info[0]
    values = _flatten_tokens(debug.get("labels_value_tokens"))

    assert "running" in values, f"Expected 'running' in label tokens, got: {values}"
    assert "waters" in values, f"Expected 'waters' in label tokens, got: {values}"
    assert "run" not in values, f"'run' should NOT be in label tokens, got: {values}"
    assert "water" not in values, (
        f"'water' should NOT be in label tokens, got: {values}"
    )


def test_linguistics_geography_synonym_expansion(vespa_app: Vespa):
    """
    Test geography query rewrites from semantic rules.

    See: https://docs.vespa.ai/en/linguistics/query-rewriting.html
    """
    doc_uk = DocumentFactory.build(
        title="xyzzygeotestuk document",
        description="A climate policy document",
        labels=[
            DocumentLabelRelationship(
                type="geography",
                value=Label(id="united-kingdom", value="United Kingdom", type="geography", labels=[]),
                timestamp=None,
            )
        ],
    )
    doc_us = DocumentFactory.build(
        title="xyzzygeotestus document",
        description="A US environmental policy document",
        labels=[
            DocumentLabelRelationship(
                type="geography",
                value=Label(id="united-states", value="United States", type="geography", labels=[]),
                timestamp=None,
            )
        ],
    )
    _feed_document(vespa_app, doc_uk)
    _feed_document(vespa_app, doc_us)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS, debug=True)
    results = engine.search(
        query="UK",
        pagination=Pagination(page_token=1, page_size=50),
        order_by=[OrderBy(field="relevance", direction="desc")],
    ).results
    result_ids = {doc.id for doc in results}

    assert doc_uk.id in result_ids, (
        f"Expected doc with geography 'United Kingdom' to match 'UK', "
        f"got ids: {result_ids}"
    )
    assert doc_us.id not in result_ids, (
        f"Doc with geography 'United States' should NOT match 'UK', "
        f"got ids: {result_ids}"
    )


# endregion Label linguistics

# region Labels schema


def test_label_search_returns_exact_match_first(vespa_app: Vespa):
    _feed_label(vespa_app, _taxonomy_vespa_label("category::Law", "category", "Law"))
    _feed_label(
        vespa_app, _taxonomy_vespa_label("category::Policy", "category", "Policy")
    )

    engine = DevVespaLabelSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query="Law",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
    ).results

    assert results, "Expected at least one result"
    assert results[0].value == "Law"


def test_label_field_filter_type_not_contains_returns_matching_type_only(
    vespa_app: Vespa,
):
    _feed_label(vespa_app, _taxonomy_vespa_label("category::Law", "category", "Law"))
    _feed_label(
        vespa_app, _taxonomy_vespa_label("geography::Romania", "geography", "Romania")
    )

    engine = DevVespaLabelSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters_json_string=Filter(
            op="and",
            filters=[FieldFilter(field="type", op="not_contains", value="category")],
        ).model_dump_json(),
    ).results

    result_ids = {label.id for label in results}
    assert "category::Law" not in result_ids
    assert "geography::Romania" in result_ids


def test_label_filter_by_nested_relationship_and_parent_id(vespa_app: Vespa):
    """``labels.type=subconcept_of AND labels.value.id=category::UN Submission``."""
    subconcept = _taxonomy_vespa_label(
        "category::Annex I",
        "category",
        "Annex I",
        labels=[_relationship("category::UN Submission", "subconcept_of")],
    )
    # Right parent, wrong relationship -> excluded by sameElement.
    wrong_relationship = _taxonomy_vespa_label(
        "category::Related Doc",
        "category",
        "Related Doc",
        labels=[_relationship("category::UN Submission", "related_to")],
    )
    # Right relationship, wrong parent -> excluded.
    wrong_parent = _taxonomy_vespa_label(
        "category::Other Sub",
        "category",
        "Other Sub",
        labels=[_relationship("category::Other Parent", "subconcept_of")],
    )
    for label in (subconcept, wrong_relationship, wrong_parent):
        _feed_label(vespa_app, label)

    engine = DevVespaLabelSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(field="labels.type", op="contains", value="subconcept_of"),
                FieldFilter(
                    field="labels.value.id",
                    op="contains",
                    value="category::UN Submission",
                ),
            ],
        ).model_dump_json(),
    ).results

    result_ids = {label.id for label in results}
    assert "category::Annex I" in result_ids
    assert "category::Related Doc" not in result_ids
    assert "category::Other Sub" not in result_ids


def test_label_filter_same_element_excludes_split_relationships(vespa_app: Vespa):
    """
    ``sameElement`` requires one related label to satisfy both conditions.

    A label with ``subconcept_of`` to one parent and ``related_to``
    category::UN Submission must NOT match a combined subconcept_of + UN
    Submission filter.
    """
    split = _taxonomy_vespa_label(
        "category::Split",
        "category",
        "Split",
        labels=[
            _relationship("category::Other Parent", "subconcept_of"),
            _relationship("category::UN Submission", "related_to"),
        ],
    )
    _feed_label(vespa_app, split)

    engine = DevVespaLabelSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters_json_string=Filter(
            op="and",
            filters=[
                FieldFilter(field="labels.type", op="contains", value="subconcept_of"),
                FieldFilter(
                    field="labels.value.id",
                    op="contains",
                    value="category::UN Submission",
                ),
            ],
        ).model_dump_json(),
    ).results

    assert "category::Split" not in {label.id for label in results}


def test_label_search_returns_non_empty_label_source(vespa_app: Vespa):
    label = _taxonomy_vespa_label("geography::Romania", "geography", "Romania")
    _feed_label(vespa_app, label)
    engine = DevVespaLabelSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query="Romania",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
    ).results
    assert isinstance(results[0], DataInLabel)
    assert results[0] is not None
    assert results[0] != ""


# endregion Labels schema
