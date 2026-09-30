"""
Validate a real documents feed op against the contract and the materializer.

Throwaway: the op lives in ``tests/fixtures/validate_document_feed_op.json``;
``test_validate_document_e2e.py`` feeds the same op into Vespa and the API.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from cpr_contracts import Document

from search.vespa.documents_feed_materializer import _source_document_to_vespa_update

FEED_OP_PATH = Path(__file__).parent / "fixtures" / "validate_document_feed_op.json"
DOC_ID_PREFIX = "id:documents:documents::"


@pytest.fixture
def feed_op() -> dict[str, Any]:
    return json.loads(FEED_OP_PATH.read_text())


def _doc_id(feed_op: dict[str, Any]) -> str:
    return feed_op["update"].removeprefix(DOC_ID_PREFIX)


def test_document_source_matches_the_materializer(feed_op: dict[str, Any]):
    """The embedded document_source passes the contract and re-materializes to this op."""
    source = feed_op["fields"]["document_source"]["assign"]
    document = Document.model_validate_json(source)
    assert document.id == _doc_id(feed_op)

    expected = json.loads(json.dumps(_source_document_to_vespa_update(document)))[
        "fields"
    ]
    expected_source = expected.pop("document_source")["assign"]
    actual = {k: v for k, v in feed_op["fields"].items() if k != "document_source"}
    # Serialised key order differs between producers, so compare the parsed model.
    assert Document.model_validate_json(expected_source) == document

    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    differing = sorted(
        k for k in expected.keys() & actual.keys() if expected[k] != actual[k]
    )
    assert (missing, extra, differing) == ([], [], []), (
        f"missing from op: {[(k, expected[k]) for k in missing]}; "
        f"not produced by the materializer: {[(k, actual[k]) for k in extra]}; "
        f"differing: {[(k, expected[k], actual[k]) for k in differing]}"
    )
