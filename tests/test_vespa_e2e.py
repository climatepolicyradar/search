"""
E2E test: AttributesCondition filters documents correctly.

Spins up an isolated Vespa container, feeds two documents (one with a
country attribute, one without), then verifies the filter returns only
the matching document.

If the test container is already running (from a previous run), it is
reused — skipping the slow deploy — and only the test documents are
cleaned up at the end. Set TEST_VESPA_REMOVE_CONTAINER=1 to remove the
container after the test.

Run with: pytest tests/test_attribute_filter_e2e.py
"""

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
import requests as req
from polyfactory.factories.typed_dict_factory import TypedDictFactory
from vespa.application import Vespa
from vespa.deployment import VespaDocker

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    AttributesCondition,
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    FieldFilter,
    Filter,
    Settings,
)
from search.vespa.documents_feed_materializer import _source_document_to_vespa_update
from search.vespa.labels_feed_materializer import (
    VespaLabel,
    _vespa_label_to_vespa_update,
)
from search.vespa.sources.data_in_api import (
    SourceDocument,
    SourceLabel,
    SourceLabelRelationship,
)

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
# we try not to use 8080 as this _might_ be the currently running local server
_PORT = 8089
_TEST_SETTINGS = Settings(
    vespa_endpoint=f"http://localhost:{_PORT}",  # type: ignore[arg-type]
    vespa_read_token="",  # nosec B106
)


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


def _vespa_ready() -> bool:
    try:
        return (
            req.get(
                f"{_TEST_SETTINGS.vespa_endpoint}state/v1/health", timeout=2
            ).status_code
            == req.codes.ok
        )
    except Exception:
        return False


@pytest.fixture(scope="module")
def vespa_app() -> Generator[Vespa, None, None]:
    remove_container = bool(os.environ.get("TEST_VESPA_REMOVE_CONTAINER"))
    vespa_docker = None
    app_dir = None

    if _vespa_ready():
        app = Vespa(url="http://localhost", port=_PORT)
    else:
        app_dir = Path(tempfile.mkdtemp())
        shutil.copytree(VESPA_APP_DIR / "schemas", app_dir / "schemas")
        shutil.copytree(
            VESPA_APP_DIR / "lucene-linguistics", app_dir / "lucene-linguistics"
        )
        shutil.copytree(VESPA_APP_DIR / "rules", app_dir / "rules")
        shutil.copy(
            Path(__file__).parent / "vespa_test_services.xml", app_dir / "services.xml"
        )
        vespa_docker = VespaDocker(port=_PORT)
        app = vespa_docker.deploy_from_disk(
            application_name="searchtestvespae2e",
            application_root=app_dir,
            max_wait_application=600,
        )

    try:
        yield app
    finally:
        if remove_container and vespa_docker and vespa_docker.container:
            vespa_docker.container.remove(force=True)
        if app_dir is not None:
            shutil.rmtree(app_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_docs(vespa_app: Vespa):
    """Delete all documents after each test for isolation."""
    yield
    vespa_app.delete_all_docs(
        content_cluster_name="search-production", schema="documents"
    )


def _feed_document(app: Vespa, document: SourceDocument) -> None:
    """Feed a document as an update operation — same format as JSONL feed."""
    op = _source_document_to_vespa_update(document)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document['id']}",
        json={**op, "create": True},
        timeout=5,
    )
    r.raise_for_status()


def _feed_document_without_title(app: Vespa, document: SourceDocument) -> None:
    """
    Feed a document update with ``title`` intentionally omitted.

    This creates a true missing ``title_sort`` value in Vespa so we can verify
    missing-title sort behaviour end-to-end.
    """
    op = _source_document_to_vespa_update(document)
    fields = dict(op.get("fields", {}))
    fields.pop("title", None)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document['id']}",
        json={**op, "fields": fields, "create": True},
        timeout=5,
    )
    r.raise_for_status()


def _ids(filter_: Filter) -> set[str]:
    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    docs = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters_json_string=filter_.model_dump_json(),
    )
    return {doc.id for doc in docs.results}


# region Attributes
def test_attribute_published_date_gte_filters_from_datetime(vespa_app: Vespa):
    document_before_range = SourceDocumentFactory.build(
        attributes={"published_date": "2019-12-31T23:59:59Z"},
        labels=[],
    )
    document_in_range = SourceDocumentFactory.build(
        attributes={"published_date": "2021-06-01T00:00:00Z"},
        labels=[],
    )
    _feed_document(vespa_app, document_before_range)
    _feed_document(vespa_app, document_in_range)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op="gte",
                value="2020-01-01T00:00:00Z",
            )
        ],
    )
    ids = _ids(f)
    assert document_before_range["id"] not in ids
    assert document_in_range["id"] in ids


def test_attribute_published_date_range_filters_inclusive(vespa_app: Vespa):
    document_before_range = SourceDocumentFactory.build(
        attributes={"published_date": "2017-06-01T00:00:00Z"},
        labels=[],
    )
    document_in_range = SourceDocumentFactory.build(
        attributes={"published_date": "2020-06-01T00:00:00Z"},
        labels=[],
    )
    document_after_range = SourceDocumentFactory.build(
        attributes={"published_date": "2024-01-01T00:00:00Z"},
        labels=[],
    )
    _feed_document(vespa_app, document_before_range)
    _feed_document(vespa_app, document_in_range)
    _feed_document(vespa_app, document_after_range)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op="gte",
                value="2019-01-01T00:00:00Z",
            ),
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op="lte",
                value="2023-12-31T23:59:59Z",
            ),
        ],
    )
    ids = _ids(f)
    assert document_before_range["id"] not in ids
    assert document_in_range["id"] in ids
    assert document_after_range["id"] not in ids


def _feed_published_date_boundary_docs(vespa_app: Vespa) -> dict[str, SourceDocument]:
    docs = {
        "before_year": SourceDocumentFactory.build(
            id="date-before-year",
            attributes={"published_date": "2019-12-31T23:59:59Z"},
            labels=[],
        ),
        "year_start": SourceDocumentFactory.build(
            id="date-year-start",
            attributes={"published_date": "2020-01-01T00:00:00Z"},
            labels=[],
        ),
        "year_end": SourceDocumentFactory.build(
            id="date-year-end",
            attributes={"published_date": "2020-12-31T23:59:59Z"},
            labels=[],
        ),
        "after_year": SourceDocumentFactory.build(
            id="date-after-year",
            attributes={"published_date": "2021-01-01T00:00:00Z"},
            labels=[],
        ),
    }
    for doc in docs.values():
        _feed_document(vespa_app, doc)
    return docs


@pytest.mark.parametrize(
    ("op", "expected_keys"),
    [
        ("lt", {"before_year"}),
        ("lte", {"before_year", "year_start", "year_end"}),
        ("gt", {"after_year"}),
        ("gte", {"year_start", "year_end", "after_year"}),
    ],
)
def test_attribute_published_date_year_operator_boundaries(
    vespa_app: Vespa, op: str, expected_keys: set[str]
):
    docs = _feed_published_date_boundary_docs(vespa_app)
    op_values = {
        "lt": "2020-01-01T00:00:00Z",
        "lte": "2020-12-31T23:59:59Z",
        "gt": "2020-12-31T23:59:59Z",
        "gte": "2020-01-01T00:00:00Z",
    }
    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op=op,  # type: ignore[arg-type]
                value=op_values[op],
            )
        ],
    )
    ids = _ids(f)
    expected_ids = {docs[key]["id"] for key in expected_keys}
    assert ids == expected_ids


def test_attribute_published_date_eq_datetime_matches_exact_timestamp(
    vespa_app: Vespa,
):
    docs = _feed_published_date_boundary_docs(vespa_app)
    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op="eq",
                value="2020-12-31T23:59:59Z",
            )
        ],
    )
    ids = _ids(f)
    assert ids == {docs["year_end"]["id"]}


def test_attribute_published_date_eq_iso_matches_exact_timestamp(vespa_app: Vespa):
    docs = _feed_published_date_boundary_docs(vespa_app)
    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op="eq",
                value="2020-01-01T00:00:00Z",
            )
        ],
    )
    ids = _ids(f)
    assert ids == {docs["year_start"]["id"]}


def test_attribute_published_date_not_eq_excludes_exact_timestamp(vespa_app: Vespa):
    docs = _feed_published_date_boundary_docs(vespa_app)
    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes.published_date",
                key="published_date",
                op="not_eq",
                value="2020-01-01T00:00:00Z",
            )
        ],
    )
    ids = _ids(f)
    assert docs["year_start"]["id"] not in ids
    assert docs["before_year"]["id"] in ids
    assert docs["year_end"]["id"] in ids
    assert docs["after_year"]["id"] in ids


# endregion Attributes


# region Labels
def _make_label(label_id: str) -> SourceLabelRelationship:
    return {
        "type": "entity_type",
        "value": SourceLabel(id=label_id, value=label_id, type="entity_type"),
        "timestamp": None,
    }


def test_labels_contains_returns_matching_doc(vespa_app: Vespa):
    doc_with_label = SourceDocumentFactory.build(labels=[_make_label("Romania")])
    doc_without_label = SourceDocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_label["id"] in ids
    assert doc_without_label["id"] not in ids


def test_labels_contains_excludes_non_matching_doc(vespa_app: Vespa):
    doc_with_different_label = SourceDocumentFactory.build(
        labels=[_make_label("France")]
    )
    doc_without_label = SourceDocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_different_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_different_label["id"] not in ids
    assert doc_without_label["id"] not in ids


def test_labels_not_contains_excludes_matching_doc(vespa_app: Vespa):
    doc_with_label = SourceDocumentFactory.build(labels=[_make_label("Romania")])
    doc_without_label = SourceDocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="not_contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_label["id"] not in ids
    assert doc_without_label["id"] in ids


def test_labels_not_contains_returns_non_matching_doc(vespa_app: Vespa):
    doc_with_different_label = SourceDocumentFactory.build(
        labels=[_make_label("France")]
    )
    doc_with_matching_label = SourceDocumentFactory.build(
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
    ids = _ids(f)
    assert doc_with_different_label["id"] in ids
    assert doc_with_matching_label["id"] not in ids


# endregion Labels

# region Concepts


def _feed_concepts(
    app: Vespa, document: SourceDocument, concept_id: str, concept_name: str
) -> None:
    """Update an existing document with a single concept."""
    # concept struct only has id/type/value/count/passages_id — no relationship/timestamp
    vespa_concepts = [
        {
            "id": concept_id,
            "type": "concept",
            "value": concept_name,
            "count": 1,
            "passages_id": "test",
        }
    ]

    update_op = {
        "update": f"id:documents:documents::{document['id']}",
        "fields": {
            "concepts": {"assign": vespa_concepts},
        },
        "create": False,
    }

    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document['id']}",
        json={"fields": update_op["fields"]},
        timeout=5,
    )
    r.raise_for_status()


def test_concepts_contains_returns_matching_doc(vespa_app: Vespa):
    doc_with_concept = SourceDocumentFactory.build(labels=[])
    doc_without_concept = SourceDocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_concept, "Romania", "Romania")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_concept["id"] in ids
    assert doc_without_concept["id"] not in ids


def test_concepts_contains_excludes_non_matching_doc(vespa_app: Vespa):
    doc_with_different_concept = SourceDocumentFactory.build(labels=[])
    doc_without_concept = SourceDocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_different_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_different_concept, "France", "France")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_different_concept["id"] not in ids
    assert doc_without_concept["id"] not in ids


def test_concepts_not_contains_excludes_matching_doc(vespa_app: Vespa):
    doc_with_concept = SourceDocumentFactory.build(labels=[])
    doc_without_concept = SourceDocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_concept, "Romania", "Romania")

    f = Filter(
        op="and",
        filters=[
            FieldFilter(field="labels.value.value", op="not_contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_concept["id"] not in ids
    assert doc_without_concept["id"] in ids


def test_concepts_not_contains_returns_non_matching_doc(vespa_app: Vespa):
    doc_with_different_concept = SourceDocumentFactory.build(labels=[])
    doc_with_matching_concept = SourceDocumentFactory.build(labels=[])
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
    ids = _ids(f)
    assert doc_with_different_concept["id"] in ids
    assert doc_with_matching_concept["id"] not in ids


# endregion Concepts


# region Linguistics
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


def test_linguistics_title_tokens_are_stemmed(vespa_app: Vespa):
    """
    Title uses passage_analysis profile: stop words removed + snowball stemming.

    "Running" should stem to "run", "waters" to "water",
    and "is" should be removed as a stop word.
    """
    doc = SourceDocumentFactory.build(
        title="Running waters is beautiful",
        description="A short description",
        labels=[],
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
    values = _flatten_tokens(debug.get("title_tokens"))

    assert "run" in values, f"Expected 'run' in title tokens, got: {values}"
    assert "water" in values, f"Expected 'water' in title tokens, got: {values}"
    assert "is" not in values, f"Stop word 'is' should be removed, got: {values}"


def test_linguistics_label_tokens_are_not_stemmed(vespa_app: Vespa):
    """
    Labels use label_analysis profile: lowercase only, no stemming.

    "Running" should become "running" (not "run").
    Search by title so userQuery() matches via the default fieldset.
    """
    doc = SourceDocumentFactory.build(
        title="Running Waters document",
        description="Test description",
        labels=[
            {
                "type": "topic",
                "value": SourceLabel(
                    id="running-waters", value="Running Waters", type="topic"
                ),
                "timestamp": None,
            }
        ],
    )
    _feed_document(vespa_app, doc)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS, debug=True)
    # Search for "running" — matches title via default fieldset
    results = engine.search(
        query="running",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
    ).results
    assert len(results) >= 1, f"Expected results, got: {results}"

    debug = engine.last_debug_info[0]
    values = _flatten_tokens(debug.get("labels_value_tokens"))

    # label_analysis: lowercase only — "Running" -> "running", not stemmed to "run"
    assert "running" in values, f"Expected 'running' in label tokens, got: {values}"
    assert "waters" in values, f"Expected 'waters' in label tokens, got: {values}"
    assert "run" not in values, f"'run' should NOT be in label tokens, got: {values}"
    assert "water" not in values, (
        f"'water' should NOT be in label tokens, got: {values}"
    )


def test_linguistics_geography_synonym_expansion(vespa_app: Vespa):
    """
    Test geography query rewrites from semantic rules.

    Note: this test could end up *not* applying to the DevVespaDocumentSearchEngine
    for valid reasons. In that case, we could remove this test or apply it to a specific
    SearchEngine.

    See: https://docs.vespa.ai/en/linguistics/query-rewriting.html
    """
    doc_uk = SourceDocumentFactory.build(
        title="xyzzygeotestuk document",
        description="A climate policy document",
        labels=[
            {
                "type": "geography",
                "value": SourceLabel(
                    id="united-kingdom", value="United Kingdom", type="geography"
                ),
                "timestamp": None,
            }
        ],
    )
    doc_us = SourceDocumentFactory.build(
        title="xyzzygeotestus document",
        description="A US environmental policy document",
        labels=[
            {
                "type": "geography",
                "value": SourceLabel(
                    id="united-states", value="United States", type="geography"
                ),
                "timestamp": None,
            }
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

    assert doc_uk["id"] in result_ids, (
        f"Expected doc with geography 'United Kingdom' to match 'UK', "
        f"got ids: {result_ids}"
    )
    assert doc_us["id"] not in result_ids, (
        f"Doc with geography 'United States' should NOT match 'UK', "
        f"got ids: {result_ids}"
    )


def test_linguistics_title_synonym_expansion(vespa_app: Vespa):
    """
    Test title acronym query rewrites from semantic rules (documents.sr).

    Searching for acronyms like "fca" or "tcfd" should match documents whose
    titles contain the expanded forms ("Financial Conduct Authority",
    "Task Force on Climate-related Financial Disclosures").
    """
    doc_with_full_forms = SourceDocumentFactory.build(
        title="Financial Conduct Authority rules on Task Force on Climate-related Financial Disclosures",
        description="A climate disclosure document",
        labels=[],
    )
    doc_without_match = SourceDocumentFactory.build(
        title="xyzzytitlesyntest unrelated environmental policy",
        description="An unrelated document",
        labels=[],
    )
    _feed_document(vespa_app, doc_with_full_forms)
    _feed_document(vespa_app, doc_without_match)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS, debug=True)
    results = engine.search(
        query="fca rules tcfd",
        pagination=Pagination(page_token=1, page_size=50),
        order_by=[OrderBy(field="relevance", direction="desc")],
    ).results
    result_ids = {doc.id for doc in results}

    assert doc_with_full_forms["id"] in result_ids, (
        f"Expected doc with expanded title to match acronym search 'fca rules tcfd', "
        f"got ids: {result_ids}"
    )
    assert doc_without_match["id"] not in result_ids, (
        f"Unrelated doc should NOT match 'fca rules tcfd', got ids: {result_ids}"
    )


# endregion Linguistics


# region Document sorting (API JSON paths via Vespa ranking.sorting)
def test_document_sort_title_sort_asc(vespa_app: Vespa):
    doc_z = SourceDocumentFactory.build(title="Zebra memo", labels=[])
    doc_a = SourceDocumentFactory.build(title="Apple brief", labels=[])
    doc_m = SourceDocumentFactory.build(title="Magpie brief", labels=[])
    doc_f = SourceDocumentFactory.build(title="Fig brief", labels=[])
    doc_missing = SourceDocumentFactory.build(
        id="e2e-title-missing-asc",
        title="Will be dropped before feed",
        labels=[],
    )
    _feed_document(vespa_app, doc_z)
    _feed_document(vespa_app, doc_a)
    _feed_document(vespa_app, doc_m)
    _feed_document(vespa_app, doc_f)
    _feed_document_without_title(vespa_app, doc_missing)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="title", direction="asc")],
    ).results

    assert [d.title for d in results[:4]] == [
        "Apple brief",
        "Fig brief",
        "Magpie brief",
        "Zebra memo",
    ]
    assert results[-1].id == "e2e-title-missing-asc"


def test_document_sort_title_sort_desc(vespa_app: Vespa):
    doc_z = SourceDocumentFactory.build(title="Zebra memo", labels=[])
    doc_a = SourceDocumentFactory.build(title="Apple brief", labels=[])
    doc_m = SourceDocumentFactory.build(title="Magpie brief", labels=[])
    doc_f = SourceDocumentFactory.build(title="Fig brief", labels=[])
    doc_missing = SourceDocumentFactory.build(
        id="e2e-title-missing-desc",
        title="Will be dropped before feed",
        labels=[],
    )
    _feed_document(vespa_app, doc_z)
    _feed_document(vespa_app, doc_a)
    _feed_document(vespa_app, doc_m)
    _feed_document(vespa_app, doc_f)
    _feed_document_without_title(vespa_app, doc_missing)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="title", direction="desc")],
    ).results

    assert [d.title for d in results[:4]] == [
        "Zebra memo",
        "Magpie brief",
        "Fig brief",
        "Apple brief",
    ]
    assert results[-1].id == "e2e-title-missing-desc"


def test_document_sort_published_timestamp_desc(vespa_app: Vespa):
    doc_old = SourceDocumentFactory.build(
        title="Old",
        labels=[],
        attributes={"published_date": "2020-01-01T00:00:00Z"},
    )
    doc_new = SourceDocumentFactory.build(
        title="New",
        labels=[],
        attributes={"published_date": "2024-06-01T12:00:00Z"},
    )
    doc_oldest = SourceDocumentFactory.build(
        title="Oldest",
        labels=[],
        attributes={"published_date": "2010-01-01T00:00:00Z"},
    )
    doc_newest = SourceDocumentFactory.build(
        title="Newest",
        labels=[],
        attributes={"published_date": "2026-06-01T12:00:00Z"},
    )
    doc_undated = SourceDocumentFactory.build(
        title="Undated",
        labels=[],
        attributes={},
    )
    _feed_document(vespa_app, doc_old)
    _feed_document(vespa_app, doc_new)
    _feed_document(vespa_app, doc_oldest)
    _feed_document(vespa_app, doc_newest)
    _feed_document(vespa_app, doc_undated)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="attributes.published_date", direction="desc")],
    ).results

    assert [d.title for d in results] == [
        "Newest",
        "New",
        "Old",
        "Oldest",
        "Undated",
    ]


def test_document_sort_published_timestamp_asc(vespa_app: Vespa):
    doc_old = SourceDocumentFactory.build(
        title="Old",
        labels=[],
        attributes={"published_date": "2020-01-01T00:00:00Z"},
    )
    doc_new = SourceDocumentFactory.build(
        title="New",
        labels=[],
        attributes={"published_date": "2024-06-01T12:00:00Z"},
    )
    doc_oldest = SourceDocumentFactory.build(
        title="Oldest",
        labels=[],
        attributes={"published_date": "2010-01-01T00:00:00Z"},
    )
    doc_newest = SourceDocumentFactory.build(
        title="Newest",
        labels=[],
        attributes={"published_date": "2026-06-01T12:00:00Z"},
    )
    doc_undated = SourceDocumentFactory.build(
        title="Undated",
        labels=[],
        attributes={},
    )
    _feed_document(vespa_app, doc_old)
    _feed_document(vespa_app, doc_new)
    _feed_document(vespa_app, doc_oldest)
    _feed_document(vespa_app, doc_newest)
    _feed_document(vespa_app, doc_undated)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="attributes.published_date", direction="asc")],
    ).results

    assert [d.title for d in results] == [
        "Oldest",
        "Old",
        "New",
        "Newest",
        "Undated",
    ]


def test_document_sort_title_asc_and_desc_first_hit_differ(vespa_app: Vespa):
    """
    First A-Z title and first Z-A title should not always be the same first row.

    If Vespa ignores ``ranking.sorting``, the same document can remain first for
    both directions; asc and desc must disagree on the leader when titles differ.

    Five docs with unambiguous lexical order; assert full permuted order, not only
    the first row.
    """
    doc_a = SourceDocumentFactory.build(
        id="e2e-sort-title-aaa",
        title="Aaa ascending leader",
        labels=[],
        attributes={"published_date": "2015-01-01T00:00:00Z"},
    )
    doc_b = SourceDocumentFactory.build(
        id="e2e-sort-title-bbb",
        title="Bbb noise",
        labels=[],
        attributes={"published_date": "2015-02-01T00:00:00Z"},
    )
    doc_m = SourceDocumentFactory.build(
        id="e2e-sort-title-mmm",
        title="Mmm middle",
        labels=[],
        attributes={"published_date": "2015-03-01T00:00:00Z"},
    )
    doc_y = SourceDocumentFactory.build(
        id="e2e-sort-title-yyy",
        title="Yyy noise",
        labels=[],
        attributes={"published_date": "2015-04-01T00:00:00Z"},
    )
    doc_z = SourceDocumentFactory.build(
        id="e2e-sort-title-zzz",
        title="Zzz descending leader",
        labels=[],
        attributes={"published_date": "2015-06-01T00:00:00Z"},
    )
    expected_asc_titles = [
        "Aaa ascending leader",
        "Bbb noise",
        "Mmm middle",
        "Yyy noise",
        "Zzz descending leader",
    ]
    expected_desc_titles = list(reversed(expected_asc_titles))
    # Deliberately not alphabetical feed order
    for doc in (doc_m, doc_z, doc_a, doc_y, doc_b):
        _feed_document(vespa_app, doc)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    asc = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="title", direction="asc")],
    ).results
    desc = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="title", direction="desc")],
    ).results
    assert [d.title for d in asc[:5]] == expected_asc_titles
    assert [d.title for d in desc[:5]] == expected_desc_titles
    assert asc[0].id == doc_a["id"], asc
    assert desc[0].id == doc_z["id"], desc
    assert asc[0].id != desc[0].id


def test_document_sort_date_desc_leader_differs_from_title_asc_leader(
    vespa_app: Vespa,
):
    """
    Newest-by-date and first A-Z title should not always be the same first row.

    Five docs: one is newest by ``attributes.published_date`` but not first by
    ``title``, so date-desc leader and title-asc leader must differ; we also
    assert full expected order for each sort mode.
    """
    doc_ancient = SourceDocumentFactory.build(
        id="e2e-sort-mixed-ancient",
        title="Zebra ancient",
        labels=[],
        attributes={"published_date": "2000-01-01T00:00:00Z"},
    )
    doc_older_a = SourceDocumentFactory.build(
        id="e2e-sort-mixed-older-a",
        title="Apple older",
        labels=[],
        attributes={"published_date": "2010-01-01T00:00:00Z"},
    )
    doc_mid = SourceDocumentFactory.build(
        id="e2e-sort-mixed-mid",
        title="Middle road",
        labels=[],
        attributes={"published_date": "2015-06-01T00:00:00Z"},
    )
    doc_newer_z = SourceDocumentFactory.build(
        id="e2e-sort-mixed-newer-z",
        title="Zebra newer",
        labels=[],
        attributes={"published_date": "2024-01-01T00:00:00Z"},
    )
    doc_newest_banana = SourceDocumentFactory.build(
        id="e2e-sort-mixed-newest-banana",
        title="Banana latest",
        labels=[],
        attributes={"published_date": "2026-06-01T12:00:00Z"},
    )
    # Title asc (lowercased): apple < banana < middle < zebra ancient < zebra newer
    expected_title_asc = [
        "Apple older",
        "Banana latest",
        "Middle road",
        "Zebra ancient",
        "Zebra newer",
    ]
    # Date desc: 2026 > 2024 > 2015 > 2010 > 2000
    expected_date_desc = [
        "Banana latest",
        "Zebra newer",
        "Middle road",
        "Apple older",
        "Zebra ancient",
    ]
    for doc in (doc_newer_z, doc_ancient, doc_older_a, doc_newest_banana, doc_mid):
        _feed_document(vespa_app, doc)

    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    by_date = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="attributes.published_date", direction="desc")],
    ).results
    by_title = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="title", direction="asc")],
    ).results
    assert [d.title for d in by_date[:5]] == expected_date_desc
    assert [d.title for d in by_title[:5]] == expected_title_asc
    assert by_date[0].id == doc_newest_banana["id"], by_date
    assert by_title[0].id == doc_older_a["id"], by_title
    assert by_date[0].id != by_title[0].id


# endregion Document sorting


# region /labels
@pytest.fixture(autouse=True)
def clean_labels(vespa_app: Vespa):
    yield
    vespa_app.delete_all_docs(content_cluster_name="search-production", schema="labels")


def _feed_label(vespa_app: Vespa, vespa_label: VespaLabel) -> None:
    vespa_update = _vespa_label_to_vespa_update(vespa_label)
    response = req.put(
        f"{vespa_app.end_point}/document/v1/labels/labels/docid/{quote(vespa_update['update'], safe='')}?create=true",
        json={"fields": vespa_update["fields"]},
        timeout=5,
    )
    if not response.ok:
        print(f"Feed label error {response.status_code}: {response.text}")
    response.raise_for_status()


def test_label_search_returns_exact_match_first(vespa_app: Vespa):
    _feed_label(
        vespa_app,
        VespaLabel(
            id="category::Law",
            type="category",
            value="Law",
            alternative_labels=[],
            subconcept_labels=[],
            description="",
            negative_labels=[],
        ),
    )
    _feed_label(
        vespa_app,
        VespaLabel(
            id="category::Policy",
            type="category",
            value="Policy",
            alternative_labels=[],
            subconcept_labels=[],
            description="",
            negative_labels=[],
        ),
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
    _feed_label(
        vespa_app,
        VespaLabel(
            id="category::Law",
            type="category",
            value="Law",
            alternative_labels=[],
            subconcept_labels=[],
            description="",
            negative_labels=[],
        ),
    )
    _feed_label(
        vespa_app,
        VespaLabel(
            id="geography::Romania",
            type="geography",
            value="Romania",
            alternative_labels=[],
            subconcept_labels=[],
            description="",
            negative_labels=[],
        ),
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


# endregion /labels
