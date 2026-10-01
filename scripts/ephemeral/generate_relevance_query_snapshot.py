"""
Regenerates scripts/ephemeral/data/relevance_query_rewrite_snapshot.json.

That snapshot pins the semantic-rule rewrite of every relevance-test query
against `main`'s rules, for scripts/ephemeral/test_relevance_query_rewrite_snapshot.py
to compare a branch's rules against. Only regenerate it deliberately, from
`main`'s actual rules - not from whatever happens to be checked out.

This is a manual, ad-hoc tool - not wired into CI - since it needs a
deliberate local redeploy against `main`'s rules specifically. Steps:
    1. Back up the current `vespa/app/rules/*.sr` files.
    2. Replace them with `main`'s: for f in documents labels passages; do
       git show main:vespa/app/rules/$f.sr > vespa/app/rules/$f.sr; done
    3. Force a fresh local deploy against those rules, e.g.:
       docker rm -f searchtestvespae2e
       uv run pytest tests/test_vespa_e2e.py -k test_get_returns_none_for_missing_id
    4. uv run python scripts/ephemeral/generate_relevance_query_snapshot.py
    5. Restore the backed-up rule files and redeploy (repeat step 3).
"""

import json
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

_PORT = 8089
_MODULE_RULEBASE = [
    (test_documents, None),
    (test_principal_documents, None),
    (test_passages, "passages"),
    (test_labels, "labels"),
]
_RULEBASE_SOURCE = {None: "documents", "passages": "passages", "labels": "labels"}

_OUT_PATH = Path(__file__).resolve().parent / "data" / "relevance_query_rewrite_snapshot.json"


def _snapshot_key(rulebase: str | None, query: str) -> str:
    return f"{rulebase or 'documents'}\x1f{query}"


def _pairs() -> list[tuple[str | None, str]]:
    pairs: set[tuple[str | None, str]] = set()
    for module, rulebase in _MODULE_RULEBASE:
        for case in module.test_cases:
            if case.search_terms:
                pairs.add((rulebase, case.search_terms))
            compare = getattr(case, "search_terms_to_compare", None)
            if compare:
                pairs.add((rulebase, compare))
    return sorted(pairs, key=lambda p: (p[0] or "", p[1]))


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
    if not isinstance(response, VespaQueryResponse):
        raise TypeError(f"expected a VespaQueryResponse, got {type(response)}")
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


def main() -> None:
    app = Vespa(url="http://localhost", port=_PORT)
    pairs = _pairs()
    print(f"{len(pairs)} unique (rulebase, query) pairs")

    snapshot = {
        _snapshot_key(rulebase, query): get_rule_rewrite(app, query, rulebase)
        for rulebase, query in pairs
    }

    _OUT_PATH.parent.mkdir(exist_ok=True)
    _OUT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(snapshot)} entries to {_OUT_PATH}")


if __name__ == "__main__":
    main()
