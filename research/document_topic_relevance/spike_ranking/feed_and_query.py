"""
SCI-807 spike: feed 5 hand-crafted documents and run 4 queries.

Validates that a `tensor<float>(topic{})` field can drive ranking via
`sum(attribute(field) * query(name))` against a query-supplied sparse tensor.

Run after `just up && just deploy` (with the topic-ranked profile deployed):

    uv run python research/document_topic_relevance/spike/feed_and_query.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import requests

VESPA = "http://localhost:8080"
SPIKE_DIR = Path(__file__).parent
DOCS_JSONL = SPIKE_DIR / "docs.jsonl"


def feed_docs() -> None:
    subprocess.run(
        ["vespa", "feed", str(DOCS_JSONL), "--target", VESPA, "--progress", "5"],
        check=True,
    )


def run_query(name: str, body: dict[str, Any]) -> None:
    print(f"\n=== {name} ===")
    print(
        f"body: {json.dumps({k: v for k, v in body.items() if k != 'yql'}, indent=2)}"
    )
    r = requests.post(f"{VESPA}/search/", json=body, timeout=10)
    r.raise_for_status()
    hits = r.json().get("root", {}).get("children", [])
    for h in hits:
        fields = h.get("fields", {})
        doc_id = fields.get("documentid", "?").rsplit("::", 1)[-1]
        rel = h.get("relevance", 0.0)
        sf = fields.get("summaryfeatures", {})
        tfidf = sf.get("topic_tfidf_score", 0.0)
        dtopic = sf.get("document_topics_score", 0.0)
        title_s = sf.get("title_score", 0.0)
        print(
            f"  {doc_id:10s} relevance={rel:8.4f}  "
            f"title_score={title_s:7.4f}  "
            f"topic_tfidf={tfidf:7.4f}  document_topics={dtopic:7.4f}"
        )


YQL = (
    "select documentid, summaryfeatures from documents "
    'where rank(principal_id contains "spike", userQuery())'
)
QUERY_TEXT = "climate finance"


def main() -> None:
    print("Feeding spike documents...")
    feed_docs()

    # 1) Baseline: text only, no topic blending.
    run_query(
        "1. baseline (nativerank, text only)",
        {
            "yql": YQL,
            "query": QUERY_TEXT,
            "ranking.profile": "nativerank",
        },
    )

    # 2) topic-ranked with tfidf signal only.
    run_query(
        "2. topic-ranked: tfidf only",
        {
            "yql": YQL,
            "query": QUERY_TEXT,
            "ranking.profile": "topic-ranked",
            "input.query(topic_tfidf_q)": {"Q13": 0.99, "Q14": 0.5},
            "input.query(topic_tfidf_weight)": 5.0,
            "input.query(document_topics_weight)": 0.0,
        },
    )

    # 3) topic-ranked with document_topics signal only.
    run_query(
        "3. topic-ranked: document_topics only",
        {
            "yql": YQL,
            "query": QUERY_TEXT,
            "ranking.profile": "topic-ranked",
            "input.query(document_topics_q)": {"Q14": 1.0},
            "input.query(topic_tfidf_weight)": 0.0,
            "input.query(document_topics_weight)": 1.0,
        },
    )

    # 4) Both signals on.
    run_query(
        "4. topic-ranked: both signals",
        {
            "yql": YQL,
            "query": QUERY_TEXT,
            "ranking.profile": "topic-ranked",
            "input.query(topic_tfidf_q)": {"Q13": 0.99, "Q14": 0.5},
            "input.query(document_topics_q)": {"Q14": 1.0},
            "input.query(topic_tfidf_weight)": 2.0,
            "input.query(document_topics_weight)": 1.0,
        },
    )


if __name__ == "__main__":
    main()
