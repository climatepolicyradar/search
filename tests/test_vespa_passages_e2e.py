"""
E2E tests for the passages schema and its parent-child references.

Spins up an isolated Vespa container (reuses one on port 8089 if already
running from a prior run — same pattern as test_vespa_e2e.py), feeds
documents and passages, and verifies imported doc-level / Principal-level
fields resolve through the schema's `reference<documents>` fields.

Set TEST_VESPA_REMOVE_CONTAINER=1 to remove the container after the test.

Run with: uv run pytest tests/test_vespa_passages_e2e.py
"""

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests as req
from cpr_contracts import Document, LabelRelationship, LabelWithoutLabelRelationships
from polyfactory.factories.pydantic_factory import ModelFactory
from vespa.application import Vespa
from vespa.deployment import VespaDocker

from search.engines.dev_vespa import Settings
from search.vespa.documents_feed_materializer import _source_document_to_vespa_update
from search.vespa.passages_feed_materializer import _text_block_to_vespa_update
from search.vespa.sources.embeddings_input_v2 import TextBlock

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
_PORT = 8089
_TEST_SETTINGS = Settings(
    vespa_endpoint=f"http://localhost:{_PORT}",  # type: ignore[arg-type]
    vespa_read_token="",  # nosec B106
)


class LabelRelationshipFactory(ModelFactory[LabelRelationship]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> LabelRelationship:
        kwargs.setdefault("timestamp", None)
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


class DocumentFactory(ModelFactory[Document]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> Document:
        if "labels" not in kwargs:
            kwargs["labels"] = [LabelRelationshipFactory.build(factory_use_construct=factory_use_construct)]
        if "documents" not in kwargs:
            kwargs["documents"] = []
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


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


@pytest.fixture(autouse=True)
def clean_passages(vespa_app: Vespa):
    """Delete all passages after each test for isolation."""
    yield
    vespa_app.delete_all_docs(
        content_cluster_name="search-production", schema="passages"
    )


def _feed_document(app: Vespa, document: Document) -> None:
    """Feed a document as an update operation — same format as JSONL feed."""
    op = _source_document_to_vespa_update(document)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={**op, "create": True},  # type: ignore[arg-type]
        timeout=5,
    )
    r.raise_for_status()


def _feed_passage(
    app: Vespa,
    block: TextBlock,
    document_id: str,
    principal_id: str | None = None,
) -> None:
    """Feed a passage as an update operation — same format as JSONL feed."""
    op = _text_block_to_vespa_update(block, document_id, principal_id=principal_id)
    r = req.put(
        f"{app.end_point}/document/v1/passages/passages/docid/{block['id']}",
        json={**op, "create": True},  # type: ignore[arg-type]
        timeout=5,
    )
    r.raise_for_status()


def _principal_label() -> LabelRelationship:
    return LabelRelationship(
        type="status",
        value=LabelWithoutLabelRelationships(id="status::Principal", type="status", value="Principal"),
        timestamp=None,)


def _text_block(
    block_id: str = "tb-1",
    text: str = "some passage text",
) -> TextBlock:
    return {
        "id": block_id,
        "idx": 0,
        "language": "en",
        "text": text,
        "type": "Text",
        "type_confidence": 0.9,
        "pages": [],
    }


def test_passage_imported_principal_id_resolves_to_parent(vespa_app: Vespa):
    """
    A passage's principal_id is imported from its parent document.

    Verifies that (a) the reference<documents> schema deploys, (b) the
    feeder assigns document_ref correctly, and (c) the imported
    principal_id is filterable on the passage side.
    """
    principal = DocumentFactory.build(
        id="principal-1",
        title="Principal doc",
        labels=[_principal_label()],
    )
    _feed_document(vespa_app, principal)
    _feed_passage(vespa_app, _text_block("tb-1"), document_id="principal-1")

    r = req.post(
        f"{vespa_app.end_point}/search/",
        json={
            "yql": 'select * from sources passages where principal_id contains "principal-1"',
            "hits": 10,
        },
        timeout=5,
    )
    r.raise_for_status()
    hits = r.json().get("root", {}).get("children", [])
    passage_ids = [hit["fields"]["id"] for hit in hits]
    assert "tb-1" in passage_ids, (
        f"Expected passage tb-1 to match principal_id filter, got: {passage_ids}"
    )


def test_passage_principal_title_resolves_via_principal_document_ref(vespa_app: Vespa):
    """
    A passage's principal_title resolves via principal_document_ref.

    principal_document_ref is a second ``reference<documents>`` on passages
    pointing at the Principal (rather than the passage's direct containing
    document). Feeds a Principal, a child document in that Principal, and
    a passage in the child; queries the passage and asserts principal_title
    resolves to the Principal's title.
    """
    principal = DocumentFactory.build(
        id="principal-climate",
        title="Climate Framework Act",
        labels=[_principal_label()],
    )
    child = DocumentFactory.build(
        id="child-1",
        title="Supporting memo",
        labels=[],
    )
    _feed_document(vespa_app, principal)
    _feed_document(vespa_app, child)
    _feed_passage(
        vespa_app,
        _text_block("tb-child"),
        document_id="child-1",
        principal_id="principal-climate",
    )

    # Query by the imported principal_title — proves the ref resolves on the
    # passage query side. Summary retrieval would need an explicit entry in
    # debug-summary, which is a separate concern.
    r = req.post(
        f"{vespa_app.end_point}/search/",
        json={
            "yql": 'select * from sources passages where principal_title contains "Climate Framework Act"',
            "hits": 10,
        },
        timeout=5,
    )
    r.raise_for_status()
    hits = r.json().get("root", {}).get("children", [])
    passage_ids = [hit["fields"]["id"] for hit in hits]
    assert "tb-child" in passage_ids, (
        f"Expected passage tb-child to match principal_title filter, got: {passage_ids}"
    )
