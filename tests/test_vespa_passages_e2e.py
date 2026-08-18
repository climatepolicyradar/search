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
from cpr_contracts import (
    Document,
    DocumentLabelRelationship,
    Label,
)
from polyfactory.factories.pydantic_factory import ModelFactory
from vespa.application import Vespa
from vespa.deployment import VespaDocker

from search.engines import Pagination
from search.engines.dev_vespa import DevVespaPassageSearchEngine, Settings
from search.vespa.documents_feed_materializer import _source_document_to_vespa_update
from search.vespa.passage import VespaLabel, VespaPassage
from search.vespa.passages_feed_materializer import _text_block_to_vespa_update
from search.vespa.sources.embeddings_input_v2 import TextBlock

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
_PORT = 8089
_TEST_SETTINGS = Settings(
    vespa_endpoint=f"http://localhost:{_PORT}",  # type: ignore[arg-type]
    vespa_read_token="",  # nosec B106
)

_HEADING_TEXT = "CARBON BUDGET FOR GRUDE EMISSIONS"
_TOC_TEXT = (
    "1. Introduction 3\n"
    "2. National circumstances 12\n"
    "3. Greenhouse gas inventory 24\n"
    "4. Policies and measures 41\n"
    "5. Conclusion 47"
)
_REFERENCES_TEXT = (
    "Smith, J. A. (2019). Climate finance in practice. Journal of Climate "
    "Policy, 12(3), 45-67. doi:10.1234/jcp.2019.001\n"
    "Jones, B. C. (2020). Adaptation pathways. Nature Climate Change, 10(2), "
    "112-119. doi:10.1234/ncc.2020.002\n"
    "Garcia, M. (2021). Mitigation costs. Energy Policy, 45, 233-241. "
    "Retrieved from https://example.org/report"
)
_PROSE_TEXT = "The carbon budget for crude emissions is 1.2 GtCO2e in 2030."


class DocumentLabelRelationshipFactory(ModelFactory[DocumentLabelRelationship]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> DocumentLabelRelationship:
        kwargs.setdefault("timestamp", None)
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


class DocumentFactory(ModelFactory[Document]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> Document:
        if "labels" not in kwargs:
            kwargs["labels"] = [DocumentLabelRelationshipFactory.build(factory_use_construct=factory_use_construct)]
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


def _feed_passage_with_labels(
    app: Vespa,
    block_id: str,
    document_id: str,
    labels: list[VespaLabel],
) -> None:
    """Feed a passage with `labels` set - the legacy materializer path doesn't set these."""
    passage = VespaPassage(
        id=block_id,
        idx=0,
        language="en",
        content="some passage text",
        document_id=document_id,
        document_ref=f"id:documents:documents::{document_id}",
        labels=labels,
    )
    r = req.put(
        f"{app.end_point}/document/v1/passages/passages/docid/{block_id}",
        json={**passage.to_vespa_update(), "create": True},  # type: ignore[arg-type]
        timeout=5,
    )
    r.raise_for_status()


def _principal_label() -> DocumentLabelRelationship:
    return DocumentLabelRelationship(
        type="status",
        value=Label(id="status::Principal", type="status", value="Principal", labels=[]),
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


def test_passage_search_preserves_currency_symbols(vespa_app: Vespa):
    """Searching a currency amount matches that amount but not a different one."""
    principal = DocumentFactory.build(id="principal-cur", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    _feed_passage(
        vespa_app,
        _text_block("tb-100", "The grant of $100 was approved."),
        document_id="principal-cur",
    )
    _feed_passage(
        vespa_app,
        _text_block("tb-1000", "The grant of $1000 was approved."),
        document_id="principal-cur",
    )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    results = engine.search(
        query="$100",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )
    ids = [p.text_block_id for p in results.results]

    assert "tb-100" in ids, f"expected the $100 passage to match '$100', got: {ids}"
    assert "tb-1000" not in ids, (
        f"the $1000 passage must not match '$100', got: {ids}"
    )
    # The stored/displayed text keeps the original symbol, not the mapped token.
    matched = next(p for p in results.results if p.text_block_id == "tb-100")
    assert "$100" in matched.text


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


def test_derived_passage_properties_are_indexed_and_filterable(vespa_app: Vespa):
    """
    For the three derived properties:

    Verifies (a) the bool fields deploy, (b) the materializer's derivations reach
    the index, and (c) a rank profile / YQL filter can read them.
    """
    document = DocumentFactory.build(id="doc-1", title="Doc", labels=[_principal_label()])
    _feed_document(vespa_app, document)
    for block_id, text in (
        ("tb-heading", _HEADING_TEXT),
        ("tb-toc", _TOC_TEXT),
        ("tb-refs", _REFERENCES_TEXT),
        ("tb-prose", _PROSE_TEXT),
    ):
        _feed_passage(vespa_app, _text_block(block_id, text=text), document_id="doc-1")

    r = req.post(
        f"{vespa_app.end_point}/search/",
        json={"yql": "select * from sources passages where true", "hits": 10},
        timeout=5,
    )
    r.raise_for_status()
    hits = r.json().get("root", {}).get("children", [])
    flags_by_id = {
        hit["fields"]["id"]: (
            hit["fields"]["looks_like_short_heading"],
            hit["fields"]["looks_like_table_of_contents"],
            hit["fields"]["looks_like_reference_list"],
        )
        for hit in hits
    }

    assert flags_by_id == {
        "tb-heading": (True, False, False),
        "tb-toc": (False, True, False),
        "tb-refs": (False, False, True),
        "tb-prose": (False, False, False),
    }


@pytest.mark.parametrize(
    ("case_id", "query", "text", "should_match"),
    [
        ("ndc", "ndc test", "The nationally determined contribution was submitted in 2021.", True),
        (
            "nature-based-solution",
            "nature based solution test",
            "The nbs programme funded mangrove restoration.",
            True,
        ),
        ("gga", "gga test", "Progress on the global goal on adaptation was reviewed.", True),
        (
            "gga-out-of-order",
            "gga test",
            # "global" and "adaptation" appear, but not as the adjacent phrase
            # "global goal adaptation" - the rule's rewrite shouldn't match this.
            "Progress on the global goal was reviewed against adaptation.",
            False,
        ),
        ("evs", "evs test", "Subsidies for electric car purchases were extended.", True),
    ],
)
def test_passage_search_applies_rulebase_rewrites(
    vespa_app: Vespa, case_id: str, query: str, text: str, should_match: bool
):
    """Searching for a term with rewrites defined in passages.sr rules matches the expanded phrase(s), not just the literal query - and does not match text where the expanded phrase's words are out of order."""
    principal = DocumentFactory.build(id=f"principal-{case_id}", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    _feed_passage(
        vespa_app,
        _text_block(f"tb-{case_id}", text),
        document_id=f"principal-{case_id}",
    )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    results = engine.search(
        query=query,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )
    ids = [p.text_block_id for p in results.results]

    if should_match:
        assert f"tb-{case_id}" in ids, (
            f"expected '{query}' rulebase rewrite to match {text!r}, got ids: {ids}"
        )
    else:
        assert f"tb-{case_id}" not in ids, (
            f"'{query}' should not match out-of-order text {text!r}, got ids: {ids}"
        )


def test_passage_labels_are_returned_and_filterable(vespa_app: Vespa):
    """
    A passage's `labels` field round-trips and is filterable.

    Verifies the schema round-trip and the `labels.value.id` filter.
    """
    document = DocumentFactory.build(id="doc-labels", labels=[_principal_label()])
    _feed_document(vespa_app, document)
    _feed_passage_with_labels(
        vespa_app,
        "tb-finance-flow",
        document_id="doc-labels",
        labels=[
            VespaLabel(
                id="concept::finance flow",
                type="concept",
                value="finance flow",
                classifier_id="classifier-1",
                end_index=12.0,
                labelled_text="finance flow",
                labellers=["classifier-1"],
                prediction_probability=0.9,
                start_index=0.0,
                timestamps=["2024-01-01T00:00:00"],
            )
        ],
    )
    _feed_passage_with_labels(
        vespa_app, "tb-drought", document_id="doc-labels", labels=[]
    )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    results = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
        filters_json_string=(
            '{"op": "and", "filters": ['
            '{"field": "labels.value.id", "op": "contains", '
            '"value": "concept::finance flow"}'
            "]}"
        ),
    )
    ids = [p.text_block_id for p in results.results]

    assert ids == ["tb-finance-flow"]
    matched = results.results[0]
    assert len(matched.labels) == 1
    assert matched.labels[0].value.id == "concept::finance flow"
    assert matched.labels[0].value.type == "concept"
    assert matched.labels[0].value.value == "finance flow"
    assert matched.labels[0].classifier_id == "classifier-1"
    # Vespa stores this as a 32-bit float, so it round-trips as the nearest
    # float32 value rather than the exact Python double.
    assert matched.labels[0].prediction_probability == pytest.approx(0.9)

