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
import re
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests as req
from polyfactory.factories.pydantic_factory import ModelFactory
from vespa.application import Vespa
from vespa.deployment import VespaDocker

from search.data_in_models import Document, Label, LabelRelationship
from search.engines import Pagination
from search.engines.dev_vespa import (
    AttributesCondition,
    DevVespaDocumentSearchEngine,
    Filter,
    LabelsCondition,
)
from search.vespa.concepts_indexer import InferenceResultInput
from search.vespa.concepts_indexer import index as index_concepts
from search.vespa.document_indexer import document_to_vespa_update

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
_PORT = 8080


def _build_services_xml() -> str:
    """Build a test services.xml, extracting the Lucene component from the real one."""
    real_services = (VESPA_APP_DIR / "services.xml").read_text()
    match = re.search(
        r"(<component\s+id=\"com\.yahoo\.language\.lucene\.LuceneLinguistics\".*?</component>)",
        real_services,
        re.DOTALL,
    )
    lucene_component = match.group(1) if match else ""
    return f"""\
<?xml version="1.0" encoding="utf-8" ?>
<services version="1.0">
    <container id="default" version="1.0">
        {lucene_component}
        <document-api/>
        <search/>
    </container>
    <content id="content" version="1.0">
        <min-redundancy>1</min-redundancy>
        <documents>
            <document type="documents" mode="index" />
        </documents>
    </content>
</services>
"""


class DocumentFactory(ModelFactory):
    __model__ = Document


def _vespa_ready() -> bool:
    try:
        return (
            req.get(
                f"{os.environ['VESPA_ENDPOINT']}/state/v1/health", timeout=2
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
            VESPA_APP_DIR / "lucene-linguistics",
            app_dir / "lucene-linguistics",
        )
        (app_dir / "services.xml").write_text(_build_services_xml())
        vespa_docker = VespaDocker(port=_PORT)
        app = vespa_docker.deploy_from_disk(
            application_name="searchtestvespae2e",
            application_root=app_dir,
        )

    try:
        yield app
    finally:
        if remove_container and vespa_docker and vespa_docker.container:
            vespa_docker.container.remove(force=True)
        if app_dir:
            shutil.rmtree(app_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_docs(vespa_app: Vespa):
    """Delete all documents after each test for isolation."""
    yield
    vespa_app.delete_all_docs(content_cluster_name="content", schema="documents")


def _feed_document(app: Vespa, document: Document) -> None:
    """Feed a document as an update operation — same format as JSONL feed."""
    op = document_to_vespa_update(document)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={**op, "create": True},
        timeout=5,
    )
    r.raise_for_status()


def _ids(filter_: Filter) -> set[str]:
    engine = DevVespaDocumentSearchEngine()
    docs = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        filters_json_string=filter_.model_dump_json(),
    )
    return {doc.id for doc in docs}


# region Attributes
def test_attribute_string_eq_returns_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"country": "UK"},
    )
    document_without_matching_attribute = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribute)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_string", key="country", op="eq", value="UK"
            )
        ],
    )
    ids = _ids(f)
    assert document_with_matching_attribute.id in ids
    assert document_without_matching_attribute.id not in ids


def test_attribute_string_not_eq_excludes_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"country": "UK"},
    )
    document_without_matching_attribute = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribute)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_string", key="country", op="not_eq", value="UK"
            )
        ],
    )
    ids = _ids(f)
    assert document_with_matching_attribute.id not in ids
    assert document_without_matching_attribute.id in ids


def test_attribute_double_eq_returns_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"project_cost_usd": 1_000_000.0},
    )
    document_without_matching_attribute = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribute)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_double",
                key="project_cost_usd",
                op="eq",
                value=1_000_000.0,
            )
        ],
    )
    ids = _ids(f)
    assert document_with_matching_attribute.id in ids
    assert document_without_matching_attribute.id not in ids


def test_attribute_double_not_eq_excludes_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"project_cost_usd": 1_000_000.0},
    )
    document_without_matching_attribute = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribute)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_double",
                key="project_cost_usd",
                op="not_eq",
                value=1_000_000.0,
            )
        ],
    )
    ids = _ids(f)
    assert document_with_matching_attribute.id not in ids
    assert document_without_matching_attribute.id in ids


def test_attribute_bool_eq_returns_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"is_active": True},
    )
    document_without_matching_attribute = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribute)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_boolean", key="is_active", op="eq", value=True
            )
        ],
    )
    ids = _ids(f)
    assert document_with_matching_attribute.id in ids
    assert document_without_matching_attribute.id not in ids


def test_attribute_bool_not_eq_excludes_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"is_active": True},
    )
    document_without_matching_attribute = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribute)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_boolean", key="is_active", op="not_eq", value=True
            )
        ],
    )
    ids = _ids(f)
    assert document_with_matching_attribute.id not in ids
    assert document_without_matching_attribute.id in ids


# endregion Attributes


# region Labels
def _make_label(label_id: str) -> LabelRelationship:
    return LabelRelationship(
        type="entity_type",
        value=Label(id=label_id, value=label_id, type="entity_type"),
    )


def test_labels_contains_returns_matching_doc(vespa_app: Vespa):
    doc_with_label = DocumentFactory.build(labels=[_make_label("Romania")])
    doc_without_label = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            LabelsCondition(field="labels.value.id", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_label.id in ids
    assert doc_without_label.id not in ids


def test_labels_contains_excludes_non_matching_doc(vespa_app: Vespa):
    doc_with_different_label = DocumentFactory.build(labels=[_make_label("France")])
    doc_without_label = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_different_label)
    _feed_document(vespa_app, doc_without_label)

    f = Filter(
        op="and",
        filters=[
            LabelsCondition(field="labels.value.id", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
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
            LabelsCondition(field="labels.value.id", op="not_contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_label.id not in ids
    assert doc_without_label.id in ids


def test_labels_not_contains_returns_non_matching_doc(vespa_app: Vespa):
    doc_with_different_label = DocumentFactory.build(labels=[_make_label("France")])
    doc_with_matching_label = DocumentFactory.build(labels=[_make_label("Romania")])
    _feed_document(vespa_app, doc_with_different_label)
    _feed_document(vespa_app, doc_with_matching_label)

    f = Filter(
        op="and",
        filters=[
            LabelsCondition(field="labels.value.id", op="not_contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_different_label.id in ids
    assert doc_with_matching_label.id not in ids


# endregion Labels

# region Concepts


def _feed_concepts(
    app: Vespa, document: Document, concept_id: str, concept_name: str
) -> None:
    """Update an existing document with a single concept."""
    inference_input: InferenceResultInput = {
        "passage_1": [
            {
                "id": concept_id,
                "name": concept_name,
                "parent_concepts": [],
                "parent_concept_ids_flat": "",
                "model": "test",
                "end": 0,
                "start": 0,
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]
    }
    op = index_concepts(document.id, inference_input)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={"fields": op["fields"]},
        timeout=5,
    )
    r.raise_for_status()


def test_concepts_contains_returns_matching_doc(vespa_app: Vespa):
    doc_with_concept = DocumentFactory.build(labels=[])
    doc_without_concept = DocumentFactory.build(labels=[])
    _feed_document(vespa_app, doc_with_concept)
    _feed_document(vespa_app, doc_without_concept)
    _feed_concepts(vespa_app, doc_with_concept, "Romania", "Romania")

    f = Filter(
        op="and",
        filters=[
            LabelsCondition(field="labels.value.id", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
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
            LabelsCondition(field="labels.value.id", op="contains", value="Romania")
        ],
    )
    ids = _ids(f)
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
            LabelsCondition(field="labels.value.id", op="not_contains", value="Romania")
        ],
    )
    ids = _ids(f)
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
            LabelsCondition(field="labels.value.id", op="not_contains", value="Romania")
        ],
    )
    ids = _ids(f)
    assert doc_with_different_concept.id in ids
    assert doc_with_matching_concept.id not in ids


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
    doc = DocumentFactory.build(
        title="Running waters is beautiful",
        description="A short description",
        labels=[],
    )
    _feed_document(vespa_app, doc)

    engine = DevVespaDocumentSearchEngine(debug=True)
    results = engine.search(
        query="running", pagination=Pagination(page_token=1, page_size=10)
    )
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
    doc = DocumentFactory.build(
        title="Running Waters document",
        description="Test description",
        labels=[
            LabelRelationship(
                type="topic",
                value=Label(id="running-waters", value="Running Waters", type="topic"),
            )
        ],
    )
    _feed_document(vespa_app, doc)

    engine = DevVespaDocumentSearchEngine(debug=True)
    # Search for "running" — matches title via default fieldset
    results = engine.search(
        query="running", pagination=Pagination(page_token=1, page_size=10)
    )
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
    Test geography synonym expansion using lucene linguistics.

    Note: this test could end up *not* applying to the DevVespaDocumentSearchEngine
    for valid reasons. In that case, we could remove this test or apply it to a specific
    SearchEngine.

    See: https://github.com/vespa-engine/sample-apps/tree/master/examples/lucene-linguistics/multiple-profiles
    """
    doc_uk = DocumentFactory.build(
        title="xyzzygeotestuk document",
        description="A climate policy document",
        labels=[
            LabelRelationship(
                type="geography",
                value=Label(
                    id="united-kingdom", value="United Kingdom", type="geography"
                ),
            )
        ],
    )
    doc_us = DocumentFactory.build(
        title="xyzzygeotestus document",
        description="A US environmental policy document",
        labels=[
            LabelRelationship(
                type="geography",
                value=Label(
                    id="united-states", value="United States", type="geography"
                ),
            )
        ],
    )
    _feed_document(vespa_app, doc_uk)
    _feed_document(vespa_app, doc_us)

    engine = DevVespaDocumentSearchEngine(debug=True)
    results = engine.search(
        query="UK", pagination=Pagination(page_token=1, page_size=50)
    )
    result_ids = {doc.id for doc in results}

    assert doc_uk.id in result_ids, (
        f"Expected doc with geography 'United Kingdom' to match 'UK', "
        f"got ids: {result_ids}"
    )
    assert doc_us.id not in result_ids, (
        f"Doc with geography 'United States' should NOT match 'UK', "
        f"got ids: {result_ids}"
    )


def test_linguistics_title_synonym_expansion(vespa_app: Vespa):
    """
    Test title synonym expansion using lucene linguistics.

    Searching for acronyms like "fca" or "tcfd" should match documents whose
    titles contain the expanded forms ("Financial Conduct Authority",
    "Task Force on Climate-related Financial Disclosures").
    """
    doc_with_full_forms = DocumentFactory.build(
        title="Financial Conduct Authority rules on Task Force on Climate-related Financial Disclosures",
        description="A climate disclosure document",
    )
    doc_without_match = DocumentFactory.build(
        title="xyzzytitlesyntest unrelated environmental policy",
        description="An unrelated document",
    )
    _feed_document(vespa_app, doc_with_full_forms)
    _feed_document(vespa_app, doc_without_match)

    engine = DevVespaDocumentSearchEngine(debug=True)
    results = engine.search(
        query="fca rules tcfd", pagination=Pagination(page_token=1, page_size=50)
    )
    result_ids = {doc.id for doc in results}

    assert doc_with_full_forms.id in result_ids, (
        f"Expected doc with expanded title to match acronym search 'fca rules tcfd', "
        f"got ids: {result_ids}"
    )
    assert doc_without_match.id not in result_ids, (
        f"Unrelated doc should NOT match 'fca rules tcfd', got ids: {result_ids}"
    )


# endregion Linguistics
