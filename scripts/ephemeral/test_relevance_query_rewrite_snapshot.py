"""
Tests the rewrite of every relevance-test query against a snapshot.

The snapshot (`tests/data/relevance_query_rewrite_snapshot.json`) is
regenerated with `scripts/ephemeral/generate_relevance_query_snapshot.py`.
Run with: uv run pytest tests/test_relevance_query_rewrite_snapshot.py
"""

import json
from pathlib import Path

import pytest
from vespa.application import Vespa

from relevance_tests import (
    test_documents,
    test_labels,
    test_passages,
    test_principal_documents,
)
from tests.vespa_e2e import get_rule_rewrite

pytest_plugins = ["tests.vespa_e2e"]

_SNAPSHOT_PATH = Path(__file__).parent / "data" / "relevance_query_rewrite_snapshot.json"
_MODULE_RULEBASE = [
    (test_documents, None),
    (test_principal_documents, None),
    (test_passages, "passages"),
    (test_labels, "labels"),
]


def _snapshot_key(rulebase: str | None, query: str) -> str:
    return f"{rulebase or 'documents'}\x1f{query}"


def _current_pairs() -> list[tuple[str | None, str]]:
    pairs: set[tuple[str | None, str]] = set()
    for module, rulebase in _MODULE_RULEBASE:
        for case in module.test_cases:
            if case.search_terms:
                pairs.add((rulebase, case.search_terms))
            compare = getattr(case, "search_terms_to_compare", None)
            if compare:
                pairs.add((rulebase, compare))
    return sorted(pairs, key=lambda p: (p[0] or "", p[1]))


_SNAPSHOT: dict[str, str] = json.loads(_SNAPSHOT_PATH.read_text())
_CASES = [
    pytest.param(rulebase, query, id=_snapshot_key(rulebase, query))
    for rulebase, query in _current_pairs()
]


@pytest.mark.parametrize(("rulebase", "query"), _CASES)
def test_relevance_query_rewrite_matches_main_snapshot(
    vespa_app: Vespa, rulebase: str | None, query: str
) -> None:
    key = _snapshot_key(rulebase, query)
    expected = _SNAPSHOT.get(key)
    if expected is None:
        pytest.fail(
            f"{key!r} is not in the snapshot - regenerate it with "
            "scripts/ephemeral/generate_relevance_query_snapshot.py"
        )

    actual = get_rule_rewrite(vespa_app, query, rulebase)

    assert actual == expected, (
        f"rewrite of {query!r} (rulebase={rulebase!r}) changed since the "
        "main snapshot was pinned - a rule change affects this "
        "relevance-test query. If intended, regenerate the snapshot with "
        "scripts/ephemeral/generate_relevance_query_snapshot.py"
    )
