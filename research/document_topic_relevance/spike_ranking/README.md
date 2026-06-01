# SCI-807 spike: rank by per-document topic relevance

Validates that a per-(document, topic) continuous score can drive Vespa ranking,
via two `tensor<float>(topic{})` fields and a `topic-ranked` rank profile. See
[Linear SCI-807](https://linear.app/climate-policy-radar/issue/SCI-807).

**Outcome: confirmed working. See [FINDINGS.md](./FINDINGS.md).**

## Run

```bash
# 1. Copy the modified documents.sd to the schema dir
cp research/document_topic_relevance/spike_ranking/documents.sd vespa/app/schemas/documents.sd

# 2. Bring up local Vespa and deploy the schema with the new fields + profile
cd vespa && just up && just deploy

# 3. Feed 5 hand-crafted docs and run 4 queries
cd ..
uv run python research/document_topic_relevance/spike_ranking/feed_and_query.py
```

## What it shows

Five docs tagged `principal_id="spike"` so the spike can run alongside any other
data already in local Vespa. Query text: `climate finance`. Topic IDs: `Q13` and
`Q14`.

| id      | title text                            | `topic_tfidf`      | `document_topics` |
| ------- | ------------------------------------- | ------------------ | ----------------- |
| spike-A | Climate finance policy …              | —                  | —                 |
| spike-B | Banana cultivation …                  | Q13: 0.98          | Q13: 1            |
| spike-C | National climate adaptation finance … | Q13: 0.5, Q14: 0.6 | Q13: 1, Q14: 1    |
| spike-D | Agricultural subsidy framework        | Q14: 0.2           | Q14: 2            |
| spike-E | Climate finance gap report            | —                  | —                 |

Per-query behaviour (see FINDINGS.md for verbatim relevance scores and the
math):

1. **Baseline (`nativerank`)** — spike-E wins on text alone; B and D have no
   text overlap (score 0).
2. **`topic-ranked`, tfidf only** (Q13:0.99, Q14:0.5, weight 5) — spike-C wins
   (text 1.42 + tfidf 3.97); spike-B leapfrogs from last to second.
3. **`topic-ranked`, document_topics only** (Q14:1) — spike-D promoted from last
   to fourth via its `document_topics` Q14:2 signal.
4. **Both signals on** (tfidf×2, document_topics×1) — spike-C clear winner with
   all three contributions.

## Files

- `docs.jsonl` — 5 docs in `vespa feed` JSONL format.
- `feed_and_query.py` — feeds via the `vespa` CLI, queries via `POST /search/`.
- `FINDINGS.md` — verbatim output, math check, and productionisation notes.

## YQL shape

```yql
select documentid, summaryfeatures from documents
where rank(principal_id contains "spike", userQuery())
```

`rank(matchCondition, scoreCondition)` constrains recall to the 5 spike docs
while keeping `userQuery()` in the _ranking_ tree so `nativeRank(title)` etc.
still fire.

## Caveats / notes

- The mapped-tensor shorthand `{"Q13": 0.98}` works directly in both feed JSON
  and query inputs. No `{"cells": [...]}` wrapping needed on this Vespa version.
- The `topic-ranked` profile degrades to `nativerank` behaviour when no tensor
  query inputs are supplied (empty tensors → `sum(...) = 0`).
- Spike docs are tagged `principal_id="spike"` purely as a recall filter so the
  spike works against a populated local cluster. Drop the filter in production.
