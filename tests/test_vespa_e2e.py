"""E2E test: AttributesCondition filters documents correctly.

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

import pytest
import requests as req
from polyfactory.factories.pydantic_factory import ModelFactory
from vespa.application import Vespa
from vespa.deployment import VespaDocker
from vespa.io import VespaQueryResponse

from search.data_in_models import Document
from search.engines.dev_vespa import AttributesCondition, Filter, _build_filter_query
from search.vespa.document_to_update_operation import document_to_vespa_update_operation

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
_PORT = 8090
_SERVICES_XML = """\
<?xml version="1.0" encoding="utf-8" ?>
<services version="1.0">
    <container id="default" version="1.0">
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
            req.get(f"http://localhost:{_PORT}/state/v1/health", timeout=2).status_code
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
        (app_dir / "services.xml").write_text(_SERVICES_XML)
        vespa_docker = VespaDocker(port=_PORT)
        app = vespa_docker.deploy_from_disk(
            application_name="testattrfilter",
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
    op = document_to_vespa_update_operation(document)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={**op, "create": True},
        timeout=5,
    )
    r.raise_for_status()


def _ids(app: Vespa, filter_: Filter) -> set[str]:
    yql = f"select * from sources documents where true{_build_filter_query(filter_)}"
    resp: VespaQueryResponse = app.query(body={"yql": yql})  # type: ignore[assignment]
    return {hit["id"].split("::")[-1] for hit in resp.hits}


def test_attribute_string_eq_returns_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"country": "UK"},
    )
    document_without_matching_attribut = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribut)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_string", key="country", op="eq", value="UK"
            )
        ],
    )
    ids = _ids(vespa_app, f)
    assert document_with_matching_attribute.id in ids
    assert document_without_matching_attribut.id not in ids


def test_attribute_string_not_eq_excludes_matching_doc(vespa_app: Vespa):
    document_with_matching_attribute = DocumentFactory.build(
        attributes={"country": "UK"},
    )
    document_without_matching_attribut = DocumentFactory.build(attributes={})
    _feed_document(vespa_app, document_with_matching_attribute)
    _feed_document(vespa_app, document_without_matching_attribut)

    f = Filter(
        op="and",
        filters=[
            AttributesCondition(
                field="attributes_string", key="country", op="not_eq", value="UK"
            )
        ],
    )
    ids = _ids(vespa_app, f)
    assert document_with_matching_attribute.id not in ids
    assert document_without_matching_attribut.id in ids


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
    ids = _ids(vespa_app, f)
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
    ids = _ids(vespa_app, f)
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
    ids = _ids(vespa_app, f)
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
    ids = _ids(vespa_app, f)
    assert document_with_matching_attribute.id not in ids
    assert document_without_matching_attribute.id in ids
