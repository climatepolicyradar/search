"""
Tests the rewrite of every relevance-test query against a snapshot.

It deploys a full local Vespa and the snapshot needs deliberate
regeneration against `main`'s rules, so it isn't suited to running on every PR.

Mismatches are displayed in the terminal before the test fails.

The snapshot (`scripts/ephemeral/data/relevance_query_rewrite_snapshot.json`)
is regenerated with `scripts/ephemeral/generate_relevance_query_snapshot.py`.

Usage: uv run pytest scripts/ephemeral/test_relevance_query_rewrite_snapshot.py -s
"""

import json
import shutil
import textwrap
from collections.abc import Generator
from pathlib import Path

from vespa.application import Vespa
from vespa.io import VespaQueryResponse

from relevance_tests import (
    test_documents,
    test_labels,
    test_passages,
    test_principal_documents,
)

pytest_plugins = ["tests.vespa_e2e"]

_SNAPSHOT_PATH = Path(__file__).parent / "data" / "relevance_query_rewrite_snapshot.json"
_MODULE_RULEBASE = [
    (test_documents, None),
    (test_principal_documents, None),
    (test_passages, "passages"),
    (test_labels, "labels"),
]
_RULEBASE_SOURCE = {None: "documents", "passages": "passages", "labels": "labels"}


def _snapshot_key(rulebase: str | None, query: str) -> str:
    return f"{rulebase or 'documents'}\x1f{query}"


def _trace_messages(node: dict | list) -> Generator[str, None, None]:
    if isinstance(node, dict):
        message = node.get("message")
        if isinstance(message, str):
            yield message
        for child in node.get("children", []):
            yield from _trace_messages(child)
    elif isinstance(node, list):
        for child in node:
            yield from _trace_messages(child)


def get_rule_rewrite(vespa_app: Vespa, query: str, rulebase: str | None) -> str:
    """
    The query as the semantic rule engine leaves it, for `query` under `rulebase`.

    Reads the `SemanticSearcher: Rewrote query: [...]` trace line, which is the
    rule engine's own output before any later stage (stemming, lowercasing,
    grouping) touches the query - so it reflects rule changes only, not noise
    from those later stages. Falls back to the pre-rule-engine parsed query when
    no rule matched, so "no rewrite happened" is still a stable, comparable value.
    """
    source = _RULEBASE_SOURCE[rulebase]
    body: dict[str, object] = {
        "yql": f"select * from sources {source} where userQuery()",
        "query": query,
        "hits": 0,
        "timeout": "5s",
        "model.language": "en",
        "tracelevel": 4,
    }
    if rulebase is not None:
        body["rules.rulebase"] = rulebase

    response = vespa_app.query(body=body)
    assert isinstance(response, VespaQueryResponse)
    messages = list(_trace_messages(response.json.get("trace", {})))

    for message in messages:
        prefix = "SemanticSearcher: Rewrote query: ["
        if message.startswith(prefix):
            return message[len(prefix) : -1]

    for message in messages:
        prefix = "Query parsed to: "
        if message.startswith(prefix):
            return message[len(prefix) :]

    raise AssertionError(f"no parsed-query trace line found for query={query!r}")


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


def _wrapped(label: str, text: str, width: int) -> str:
    indent = " " * (len(label) + 2)
    return textwrap.fill(
        text, width=width, initial_indent=f"{label}: ", subsequent_indent=indent
    )


def _print_mismatch_table(mismatches: list[tuple[str | None, str, str, str]]) -> None:
    width = max(shutil.get_terminal_size(fallback=(100, 24)).columns - 2, 60)
    divider = "-" * width

    print(f"\n{len(mismatches)} relevance-test quer{'y' if len(mismatches) == 1 else 'ies'} "
          "changed rewrite since the main snapshot was pinned:\n")
    for rulebase, query, expected, actual in mismatches:
        print(divider)
        print(_wrapped("Query", query, width))
        print(_wrapped("Rulebase", rulebase or "documents", width))
        print(_wrapped("Main (expected)", expected, width))
        print(_wrapped("Branch (actual)", actual, width))
    print(divider)
    print()


def test_relevance_query_rewrites_match_main_snapshot(vespa_app: Vespa) -> None:
    mismatches: list[tuple[str | None, str, str, str]] = []
    missing_keys: list[str] = []

    for rulebase, query in _current_pairs():
        key = _snapshot_key(rulebase, query)
        expected = _SNAPSHOT.get(key)
        if expected is None:
            missing_keys.append(key)
            continue

        actual = get_rule_rewrite(vespa_app, query, rulebase)
        if actual != expected:
            mismatches.append((rulebase, query, expected, actual))

    if mismatches:
        _print_mismatch_table(mismatches)

    if missing_keys:
        print(f"\n{len(missing_keys)} quer(y/ies) missing from the snapshot - regenerate it "
              "with scripts/ephemeral/generate_relevance_query_snapshot.py:")
        for key in missing_keys:
            print(f"  {key!r}")

    if mismatches or missing_keys:
        raise AssertionError(
            f"{len(mismatches)} rewrite(s) changed and {len(missing_keys)} "
            "quer(y/ies) missing from the main snapshot - see the table above"
        )
