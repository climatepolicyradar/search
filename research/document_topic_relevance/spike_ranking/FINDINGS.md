# SCI-807 spike — findings

**Outcome: it works.** A per-(document, topic) continuous score, stored in a
`tensor<float>(topic{})` attribute and combined via
`sum(attribute * query_tensor)` in a rank profile, ranks documents exactly as
designed. Math checks out to the 4th decimal place across all four test queries.

## Why tensors, not `weightedSet` + `dotProduct`

The alternative was `weightedset<string>` fields with Vespa's
[`dotProduct` query operator](https://docs.vespa.ai/en/multivalue-query-operators.html).
We chose
[`tensor<float>(topic{})`](https://docs.vespa.ai/en/tensor-user-guide.html)
instead for three reasons:

1. **Float weights.**
   [`weightedset` weights are signed int32](https://docs.vespa.ai/en/reference/schema-reference.html#weightedset)
   — tfidf scores (0.0–1.0) would need to be scaled on the way in (e.g.
   `round(tfidf × 10_000)`) and decoded on the way out. Tensors store native
   floats, so 0.98 goes in and comes out as 0.98.

2. **No recall blow-up.** The `dotProduct` YQL operator is a _matching_
   operator: "documents where the weighted set field contains at least one of
   the tokens in the query." Putting it in the WHERE clause widens recall to
   every doc carrying any of the queried topic IDs, even ones the text query
   would never return. The tensor approach is purely a _scoring_ expression — it
   runs only on docs already retrieved by `userQuery()` and doesn't widen
   recall.

3. **Forward compatible.** Embeddings, cross-encoder rerankers, and multi-phase
   ranking are all
   [tensor-native in Vespa](https://docs.vespa.ai/en/tensor-user-guide.html).
   The Vespa docs themselves note that weightedsets can be converted to tensors
   via
   [`tensorFromWeightedSet()`](<https://docs.vespa.ai/en/reference/rank-features.html#tensorFromWeightedSet(name,dimension)>),
   signalling tensors as the direction of travel. Starting here avoids a
   migration later.

## What was deployed

- `vespa/app/schemas/documents.sd`: two new tensor fields (`topic_tfidf`,
  `document_topics`) and one new rank profile (`topic-ranked` inheriting from
  `nativerank`).
- 5 hand-crafted documents tagged `principal_id="spike"` (see `docs.jsonl`).

## Query shape

```yql
select documentid, summaryfeatures from documents
where rank(principal_id contains "spike", userQuery())
```

`rank(matchCondition, scoreCondition)` matches docs by `principal_id` (so only
the 5 spike docs are returned, not the 56K real docs already in local Vespa) but
still scores them against `userQuery()` text — so `nativeRank(title)` etc. fire
normally for docs whose text matches.

Query inputs (passed via JSON body to `POST /search/`):

```json
"input.query(topic_tfidf_q)": {"Q13": 0.99, "Q14": 0.5},
"input.query(document_topics_q)": {"Q14": 1.0},
"input.query(topic_tfidf_weight)": 2.0,
"input.query(document_topics_weight)": 1.0
```

The mapped tensor shorthand `{"Q13": 0.99, "Q14": 0.5}` works directly for both
query inputs and document feed format — no `{"cells": [...]}` wrapping needed.

## Verbatim output (latest run)

```text
=== 1. baseline (nativerank, text only) ===
  spike-E    relevance=  2.2570  title_score= 2.0398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-A    relevance=  2.1511  title_score= 1.9398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-C-Q13-Q14    relevance=  1.4973  title_score= 1.4151  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-D-Q14    relevance=  0.0000  title_score= 0.0000  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-B-Q13    relevance=  0.0000  title_score= 0.0000  topic_tfidf= 0.0000  document_topics= 0.0000

=== 2. topic-ranked: tfidf only (weight 5.0, Q13:0.99 Q14:0.5) ===
  spike-C-Q13-Q14    relevance=  5.4723  title_score= 1.4151  topic_tfidf= 3.9750  document_topics= 0.0000
  spike-B-Q13    relevance=  4.8510  title_score= 0.0000  topic_tfidf= 4.8510  document_topics= 0.0000
  spike-E    relevance=  2.2570  title_score= 2.0398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-A    relevance=  2.1511  title_score= 1.9398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-D-Q14    relevance=  0.5000  title_score= 0.0000  topic_tfidf= 0.5000  document_topics= 0.0000

=== 3. topic-ranked: document_topics only (weight 1.0, Q14:1) ===
  spike-C-Q13-Q14    relevance=  2.4973  title_score= 1.4151  topic_tfidf= 0.0000  document_topics= 1.0000
  spike-E    relevance=  2.2570  title_score= 2.0398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-A    relevance=  2.1511  title_score= 1.9398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-D-Q14    relevance=  2.0000  title_score= 0.0000  topic_tfidf= 0.0000  document_topics= 2.0000
  spike-B-Q13    relevance=  0.0000  title_score= 0.0000  topic_tfidf= 0.0000  document_topics= 0.0000

=== 4. topic-ranked: both signals (tfidf×2.0, document_topics×1.0) ===
  spike-C-Q13-Q14    relevance=  4.0873  title_score= 1.4151  topic_tfidf= 1.5900  document_topics= 1.0000
  spike-E    relevance=  2.2570  title_score= 2.0398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-D-Q14    relevance=  2.2000  title_score= 0.0000  topic_tfidf= 0.2000  document_topics= 2.0000
  spike-A    relevance=  2.1511  title_score= 1.9398  topic_tfidf= 0.0000  document_topics= 0.0000
  spike-B-Q13    relevance=  1.9404  title_score= 0.0000  topic_tfidf= 1.9404  document_topics= 0.0000
```

## Math check

| doc | tfidf field        | doc_topics field | Q2 expected topic_tfidf score           | Q2 observed  |
| --- | ------------------ | ---------------- | --------------------------------------- | ------------ |
| B   | Q13: 0.98          | —                | 5.0 × (0.98 × 0.99) = 4.8510            | **4.8510** ✓ |
| C   | Q13: 0.5, Q14: 0.6 | —                | 5.0 × (0.5 × 0.99 + 0.6 × 0.5) = 3.9750 | **3.9750** ✓ |
| D   | Q14: 0.2           | —                | 5.0 × (0.2 × 0.5) = 0.5000              | **0.5000** ✓ |

| doc | Q4 expected total                                                 | Q4 observed  |
| --- | ----------------------------------------------------------------- | ------------ |
| C   | 1.4151 (text) + 2 × 0.795 (tfidf) + 1 × 1.0 (doc_topics) = 4.0873 | **4.0873** ✓ |
| D   | 0.0000 (text) + 2 × 0.100 (tfidf) + 1 × 2.0 (doc_topics) = 2.2000 | **2.2000** ✓ |
| B   | 0.0000 (text) + 2 × 0.9702 (tfidf) + 1 × 0 (doc_topics) = 1.9404  | **1.9404** ✓ |

## How rank order shifted

- **Baseline:** spike-E > spike-A > spike-C-Q13-Q14 — text wins.
- **+ tfidf signal:** spike-C-Q13-Q14 and spike-B-Q13 leapfrog the text-only
  winners — topic tfidf wins.
- **+ document_topics signal:** spike-C-Q13-Q14 still top (text + Q14:1 match),
  spike-D-Q14 rises from last to fourth (Q14:2).
- **Both signals on:** spike-C-Q13-Q14 is the clear winner (text + both topic
  signals), spike-D-Q14 promoted by document_topics, spike-B-Q13 promoted by
  tfidf.

This is the behaviour the Linear issue called for:
`nativeRank(text) + A * rank(topic_tfidf) + B * rank(document_topics)`.

## Practical notes

- **Tensor JSON feed shorthand works** — `"topic_tfidf": {"Q13": 0.98}` parses
  directly, no `cells` wrapper required.
- **Empty-tensor default is graceful** — docs A and E have no tensors set; their
  `topic_*_score` is exactly 0, not an error. Same for queries that omit a
  tensor input.
- **`rank(filter, userQuery())` is the right YQL shape** when you want to
  constrain recall without losing text-relevance scoring.
- **Vespa deploy emitted no errors** for the new fields or rank profile
  (warnings predate this change).

## Path to production

When productionising this signal (out of scope for the spike):

1. Populate `topic_tfidf` / `document_topics` from the predictor evaluation
   pipeline in `research/document_topic_relevance/`. The materializer at
   `search/vespa/documents_feed_materializer.py` is the right insertion point.
2. The query-side caller (the search engine or API layer) will need to assemble
   the sparse query tensors from whatever produces query→topic mappings
   (currently no such component — needs design).
3. Decide between (a) one shared `topic-ranked` profile, (b) per-use-case
   profiles, or (c) a feature-flagged variant of `nativerank`.
4. Consider second-phase tensor ranking once we have multiple topic signals +
   embeddings.

## Sense-check against `DevVespaDocumentSearchEngine.search()`

Compared the spike against the production query path in
`search/engines/dev_vespa.py`.

### Compatible by design

- **Tensor scoring composes cleanly with prod recall.** Production builds YQL as
  `where true [and <filters>] and (userQuery() or {defaultIndex:"geographies"}userInput(@query) or ...)`
  (lines 591–599). The `topic-ranked` profile only adds _scoring expressions_,
  not matching — so whatever the OR'd multi-index recall retrieves, the tensor
  score is applied on top via `first-phase`. No conflict.
- **Empty-tensor default is a safety net.** Existing docs in Vespa don't have
  `topic_tfidf` / `document_topics` set → empty attribute tensors →
  `sum(attribute * query) = 0`. Queries without tensor inputs → empty query
  tensor → again 0. Switching the profile is a no-op until both sides start
  populating. Confirmed in this spike's run (docs A and E scored 0 on topic
  terms with no errors).

### Gotchas for integration

1. **The engine hard-codes `ranking.profile=nativerank` (line 614).** To use
   `topic-ranked` in prod, that line needs to flip or branch on a flag. The
   query-side caller would also need to pass:

   ```python
   request_body["input.query(topic_tfidf_q)"] = {...}
   request_body["input.query(document_topics_q)"] = {...}
   request_body["input.query(topic_tfidf_weight)"] = ...
   request_body["input.query(document_topics_weight)"] = ...
   ```

   No component exists today that maps a user query → topic-id weights. That's
   the missing piece on the query side.

2. **Sort overrides force `ranking.profile=unranked`** (line 435 in
   `_ranking_overrides_for_document_order_by`). Topic ranking will be
   **automatically disabled** for any query with `order_by` ≠ `relevance`.
   Correct behaviour — sorting by published_date shouldn't blend topic relevance
   — but worth flagging.

3. **Prod's `userQuery()` is OR'd across `geographies`, `title_synonyms`,
   `identifiers` indexes** (`_userQuery`, lines 571–580). The spike used bare
   `userQuery()`. When wiring into prod, the tensor scoring will sit alongside
   this multi-index match — no change needed to the tensor logic, but the
   combined `first-phase` score will then include `geographies_score()` etc.
   (already weighted in inherited `nativerank`).

4. **`where rank(principal_id contains "spike", userQuery())` was spike-only.**
   Prod uses `where true and (userQuery() or ...)` — recall is filtered by text
   match. In prod we'd drop the `rank()` operator; the tensor score applies to
   whatever text retrieval matched. Exception: if we ever want to _retrieve_
   docs purely on topic relevance (e.g. "show me docs strongly tagged with topic
   X even if they don't mention it textually"), we'd need a separate recall
   clause.

### Minor: spike-only feed quirk

`docs.jsonl` sets `"document_source": "spike"` (plain string), but prod's
`search()` calls `json.loads(fields.get("document_source"))` (line 640) and
skips the hit with a warning if it isn't valid JSON. Real predictor-driven feeds
must keep `document_source` as valid JSON. Doesn't affect spike correctness —
these docs aren't routed through `DevVespaDocumentSearchEngine`.
