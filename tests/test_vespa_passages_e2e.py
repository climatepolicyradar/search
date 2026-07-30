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
from search.vespa.passages_feed_materializer import _text_block_to_vespa_update
from search.vespa.sources.embeddings_input_v2 import TextBlock

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
_PORT = 8089
_TEST_SETTINGS = Settings(
    vespa_endpoint=f"http://localhost:{_PORT}",  # type: ignore[arg-type]
    vespa_read_token="",  # nosec B106
)


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


def test_quoted_passage_search_is_literal_phrase_match(vespa_app: Vespa):
    """A double-quoted query matches only the literal phrase."""
    principal = DocumentFactory.build(id="principal-exact", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    passages = {
        "tb-exact": "The National Strategy for Climate Change 2050 sets the target.",
        # Differs only by a stop word that passage_analysis removes.
        "tb-stopword": "The National Strategy on Climate Change 2050 sets the target.",
        # Differs only by inflections that snowballPorter strips.
        "tb-stemmed": "The National Strategies for Climate Changes 2050 set the targets.",
    }
    for block_id, text in passages.items():
        _feed_passage(
            vespa_app,
            _text_block(block_id, text),
            document_id="principal-exact",
        )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    results = engine.search(
        query='"national strategy for climate change 2050"',
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )
    ids = [p.text_block_id for p in results.results]

    assert ids == ["tb-exact"], (
        "a quoted query must return only the literal phrase; "
        f"got: {ids} (stop-word/stemmed near-misses must be excluded)"
    )


def test_quoted_passage_search_preserves_currency_symbols(vespa_app: Vespa):
    """
    A quoted currency amount matches that amount and not a longer one.

    `exact_analysis` keeps the currency charFilters, so "$100" analyzes to
    `dollar100` on both the index and query side of the quoted path. This is the
    stage that makes the linguistics tokenizer non-negotiable in
    `_EXACT_PHRASE_YQL`: Vespa's internal query tokenizer strips the "$" before
    any analyzer runs, so it would search for `100` and match nothing.
    """
    principal = DocumentFactory.build(id="principal-qcur", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    passages = {
        "tb-q100": "The grant of $100 was approved.",
        # `dollar1000` is a different token from `dollar100`.
        "tb-q1000": "The grant of $1000 was approved.",
        # Indexes as two tokens (`dollar`, `100`), so the single-token phrase
        # term cannot match it.
        "tb-qspaced": "The grant of $ 100 was approved.",
        # The charFilter maps the symbol to `dollar` glued to the amount, so the
        # spelled-out form is a distinct token sequence.
        "tb-qwords": "The grant of 100 dollars was approved.",
    }
    for block_id, text in passages.items():
        _feed_passage(
            vespa_app, _text_block(block_id, text), document_id="principal-qcur"
        )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    for query in ('"$100"', '"grant of $100"'):
        results = engine.search(
            query=query,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )
        ids = [p.text_block_id for p in results.results]
        assert ids == ["tb-q100"], (
            f"quoted {query} must match only the literal $100 passage, got: {ids}"
        )


def test_quoted_passage_search_punctuation_limits(vespa_app: Vespa):
    """
    Quoting cannot distinguish punctuation the tokenizer discards.

    Only `$`, `€` and `£` survive analysis, because `exact_analysis` has explicit
    charFilters for them. Everything else is dropped by the standard tokenizer,
    so a quoted phrase is literal in its *words* but not in its punctuation:
    "nature-based" and "nature based" both index as `[nature, based]`, and "40%"
    indexes as `[40]`.

    Asserted rather than left implicit so the boundary of "exact match" is
    written down - if a product decision needs `%` or hyphens to be
    distinguishable, that is a new charFilter in `exact_analysis`, not a query
    change. Inflection is still distinguished (see the singular case), which is
    what `stemming: none` buys.
    """
    principal = DocumentFactory.build(id="principal-punct", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    passages = {
        "tb-hyphen": "We fund nature-based solutions widely.",
        "tb-space": "We fund nature based solutions widely.",
        "tb-singular": "We fund nature-based solution widely.",
        "tb-pct": "Emissions fell 40% last year.",
        "tb-pct-words": "Emissions fell 40 percent last year.",
    }
    for block_id, text in passages.items():
        _feed_passage(
            vespa_app, _text_block(block_id, text), document_id="principal-punct"
        )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)

    def search(query: str) -> list[str]:
        results = engine.search(
            query=query,
            pagination=Pagination(page_token=1, page_size=10),
            order_by=[],
        )
        return sorted(p.text_block_id for p in results.results)

    # The hyphen is not a distinguishing feature: both spellings match either way.
    assert search('"nature-based solutions"') == ["tb-hyphen", "tb-space"]
    assert search('"nature based solutions"') == ["tb-hyphen", "tb-space"]
    # ...but the plural still is, because nothing stems this field.
    assert search('"nature-based solution"') == ["tb-singular"]
    # `%` is discarded, so it cannot separate "40%" from "40 percent".
    assert search('"fell 40%"') == ["tb-pct", "tb-pct-words"]


def test_quoted_passage_search_requires_adjacency_and_order(vespa_app: Vespa):
    """A quoted query is a phrase, not a bag of words: order and adjacency matter."""
    principal = DocumentFactory.build(id="principal-order", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    passages = {
        "tb-phrase": "A just transition for coal regions is required.",
        "tb-reordered": "A transition just for coal regions is required.",
        "tb-split": "A just and equitable transition for coal regions is required.",
    }
    for block_id, text in passages.items():
        _feed_passage(
            vespa_app,
            _text_block(block_id, text),
            document_id="principal-order",
        )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    results = engine.search(
        query='"just transition"',
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )
    ids = [p.text_block_id for p in results.results]

    assert ids == ["tb-phrase"], (
        f"expected only the adjacent, in-order phrase to match, got: {ids}"
    )


def test_unquoted_passage_search_is_unaffected_by_exact_field(vespa_app: Vespa):
    """An unquoted query still goes through userQuery() against `text`."""
    principal = DocumentFactory.build(id="principal-plain", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    _feed_passage(
        vespa_app,
        _text_block("tb-plain", "The National Strategy for Climate Change 2050."),
        document_id="principal-plain",
    )

    engine = DevVespaPassageSearchEngine(_TEST_SETTINGS)
    results = engine.search(
        query="national strategies",
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[],
    )
    ids = [p.text_block_id for p in results.results]

    assert ids == ["tb-plain"], (
        f"unquoted queries must still stem: expected tb-plain, got: {ids}"
    )


def test_passage_fields_tokenize_differently(vespa_app: Vespa):
    """
    `text` is stemmed and stop-word-filtered; `text_not_stemmed` is neither.

    This is the invariant the quoted-search path depends on. Asserting it
    directly means a linguistics regression points at the analyzer config rather
    than surfacing as a puzzling search result.
    """
    principal = DocumentFactory.build(id="principal-tokens", labels=[_principal_label()])
    _feed_document(vespa_app, principal)
    _feed_passage(
        vespa_app,
        _text_block("tb-tokens", "National Strategy for Climate Change 2050"),
        document_id="principal-tokens",
    )

    r = req.post(
        f"{vespa_app.end_point}/search/",
        json={
            "yql": 'select * from sources passages where id contains "tb-tokens"',
            "hits": 1,
            "presentation.summary": "debug-summary",
        },
        timeout=5,
    )
    r.raise_for_status()
    fields = r.json()["root"]["children"][0]["fields"]

    def _flatten(tokens: list[Any]) -> list[str]:
        """stemming: multiple yields a list of alternatives per position."""
        return [t if isinstance(t, str) else t[0] for t in tokens]

    stemmed = _flatten(fields["text_tokens"])
    literal = _flatten(fields["text_not_stemmed_tokens"])

    assert "for" not in stemmed, f"expected the stop word dropped from text: {stemmed}"
    assert "strategi" in stemmed, f"expected text stemmed: {stemmed}"
    assert literal == [
        "national",
        "strategy",
        "for",
        "climate",
        "change",
        "2050",
    ], f"text_not_stemmed must be lowercased only: {literal}"


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
