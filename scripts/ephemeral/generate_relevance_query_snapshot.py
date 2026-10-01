"""
Regenerates tests/data/relevance_query_rewrite_snapshot.json.

That snapshot pins the semantic-rule rewrite of every relevance-test query
against `main`'s rules, for tests/test_relevance_query_rewrite_snapshot.py to
compare a branch's rules against. Only regenerate it deliberately, from
`main`'s actual rules - not from whatever happens to be checked out.

Steps:
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
from pathlib import Path

from vespa.application import Vespa

from relevance_tests import (
    test_documents,
    test_labels,
    test_passages,
    test_principal_documents,
)
from tests.vespa_e2e import _PORT, get_rule_rewrite

_MODULE_RULEBASE = [
    (test_documents, None),
    (test_principal_documents, None),
    (test_passages, "passages"),
    (test_labels, "labels"),
]

_OUT_PATH = Path(__file__).resolve().parents[2] / "tests" / "data" / "relevance_query_rewrite_snapshot.json"


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


def main() -> None:
    app = Vespa(url="http://localhost", port=_PORT)
    pairs = _pairs()
    print(f"{len(pairs)} unique (rulebase, query) pairs")

    snapshot = {
        _snapshot_key(rulebase, query): get_rule_rewrite(app, query, rulebase)
        for rulebase, query in pairs
    }

    _OUT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(snapshot)} entries to {_OUT_PATH}")


if __name__ == "__main__":
    main()
