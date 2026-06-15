# Document–topic relevance: predictor findings

> [!WARNING] This document is a Claude-generated summary of the chat that
> produced this code (with carefully placed human intervention). It's included
> as an accurate representation of the findings whilst building out the set of
> predictors, but proceed with caution when looking at any finer points implied
> in the language used here.

Summary of the predictor experiments for
[SCI-802](https://linear.app/climate-policy-radar/issue/SCI-802/create-and-evaluate-new-predictors).
Full metrics are regenerated into [PREDICTOR_METRICS.md](./PREDICTOR_METRICS.md)
(predictor leaderboards) and [THRESHOLD_TUNING.md](./THRESHOLD_TUNING.md) (tuned
thresholds + cross-validated scores).

## Task & data

Predict the relevance of a (document, topic) pair on a ternary scale: `0` not
relevant, `1` marginally relevant, `2` highly relevant. Ground truth is a
hand-labelled set of **784 pairs over 49 documents × 16 topics**, heavily
imbalanced (582 / 129 / 73 for classes 0 / 1 / 2 → 202 "relevant" of either
degree).

Each pair is enriched with passage-level mention data from Snowflake
(`UNIFIED_PASSAGE_TOPICS` joined to `PIPELINE_PASSAGES_V1`): per-mention passage
index, page number and section, plus per-document totals, per-section sizes and
per-page passage counts. Each topic also carries its **corpus-wide frequency**
(collection frequency = total passage occurrences; document frequency = distinct
documents mentioning it) — the IDF input for the TF-IDF predictors. Topics join
to the warehouse on `Label.value` ↔ `TOPIC_NAME`.

## Methodology

- **Predictors** are `ThresholdPredictor`s: each computes one continuous feature
  and maps it to `{0,1,2}` via two thresholds (`low`, `high`). A predictor
  returns `0` whenever the topic isn't mentioned at all.
- **TF-IDF predictors** weight an in-document mention signal (TF: raw `count`,
  `density` = count ÷ total passages, or `lognorm` = 1 + log count) by topic
  rarity across the corpus (IDF: `df` = inverse document frequency, `cf` =
  inverse collection frequency). IDF is a per-topic constant.
- **Thresholds are tuned** by grid search over feature quantiles, with
  **document-grouped cross-validation** (whole documents held out per fold) so
  thresholds don't peek at the documents they're scored on. Objective =
  **macro-F1 over classes 1 & 2** (class 0 ignored). The honest number is the CV
  mean; the full-set fit is optimistic.
- **NDCG** measures ranking quality of the raw continuous feature against the
  graded `{0,1,2}` labels, threshold-independent. _By document_ ranks each
  document's topics — the "most relevant topics for a document" view, and the
  one IDF can improve. _By topic_ ranks documents within a topic and is
  invariant to per-topic constants (so IDF can't change it). _Global pooled_
  ranks all pairs together.
- **Caveat throughout:** with only 49 documents, treat differences under
  ~0.02–0.03 (F1 or NDCG) as noise.

## Headline results — classification

Tuned, document-grouped cross-validated F1 on classes 1 & 2 (the honest,
held-out number to trust):

| Predictor              | CV F1(1&2) | tuned (low, high) | feature                                   |
| ---------------------- | ---------: | ----------------- | ----------------------------------------- |
| **mention-density**    |  **0.591** | (0.0019, 0.045)   | mentions ÷ total passages                 |
| tfidf-density-cf       |      0.585 | (0.0097, 0.095)   | density × inverse collection frequency    |
| tfidf-density-df       |      0.580 | (0.0017, 0.031)   | density × inverse document frequency      |
| decay-weighted         |      0.573 | (1.98, 97.4)      | mentions weighted by 1/position decay     |
| first-10-pages         |      0.572 | (0, 7)            | # mentions in first 10 pages              |
| first-10-pages-density |      0.566 | (0, 0.016)        | mention density within first 10 pages     |
| first-5-pages          |      0.558 | (0, 3)            | # mentions in first 5 pages               |
| mention-count          |      0.550 | (3.7, 309)        | raw # mention passages                    |
| max-mentions-per-page  |      0.539 | (2, 11.2)         | peak mentions on any page                 |
| tfidf-count-cf         |      0.536 | (20.7, 404)       | count × inverse collection frequency      |
| first-15-pages         |      0.533 | (0, 11)           | # mentions in first 15 pages              |
| earliest-mention-page  |      0.517 | (2, 43.2)         | page of earliest mention (smaller better) |
| tfidf-count-df         |      0.504 | (3.8, 73.6)       | count × inverse document frequency        |
| first-fraction         |      0.476 | (1.5, 16)         | # mentions in first 15% of passages       |
| earliest-mention       |      0.460 | (0.38, 0.99)      | earliness = 1 − first_idx/total           |
| first-3-pages          |      0.455 | (0, 1)            | # mentions in first 3 pages               |
| max-section-density    |      0.446 | (0.091, 1)        | peak mention density within a section     |
| tfidf-lognorm-df       |      0.303 | (0.29, 3.5)       | (1 + log count) × inverse doc frequency   |

On the **pointwise CV objective** the TF-IDF density variants are a statistical
tie with the best plain feature (0.585 / 0.580 vs `mention-density` 0.591). But
once the (full-set, tuned) predictions are **aggregated per group** — the way
you actually use them — the density variants pull ahead (PREDICTOR_METRICS.md):

| Predictor        | pointwise F1(1&2) | by-document F1(1&2) | by-topic F1(1&2) |
| ---------------- | ----------------: | ------------------: | ---------------: |
| tfidf-density-cf |             0.615 |           **0.567** |            0.541 |
| tfidf-density-df |             0.609 |               0.556 |        **0.558** |
| mention-density  |             0.615 |               0.546 |            0.510 |

So `mention-density` and `tfidf-density-cf` tie pooled, but both density TF-IDF
variants beat plain density once you average per document or per topic. (These
per-group F1s use full-set-optimal thresholds, so they're optimistic — the
threshold-independent NDCG below is the cleaner evidence.) The count variants
are mid-pack and `lognorm` is the worst predictor tried.

## Headline results — ranking quality (NDCG)

From PREDICTOR_METRICS.md (threshold-independent, so valid despite the
placeholder note above), sorted by NDCG **by document** — the "best topics for a
document" goal:

| Predictor               | NDCG by document | NDCG global pooled | NDCG by topic |
| ----------------------- | ---------------: | -----------------: | ------------: |
| **tfidf-density-cf**    |        **0.939** |              0.950 |         0.921 |
| tfidf-count-cf          |            0.939 |              0.952 |         0.878 |
| tfidf-density-df        |            0.928 |              0.939 |         0.921 |
| tfidf-count-df          |            0.928 |              0.949 |         0.878 |
| mention-count           |            0.919 |              0.954 |         0.878 |
| mention-density         |            0.919 |              0.950 |         0.921 |
| first-15-pages          |            0.912 |              0.960 |         0.863 |
| decay-weighted          |            0.910 |              0.954 |         0.875 |
| first-10-pages-density  |            0.909 |              0.945 |         0.845 |
| first-10-pages          |            0.906 |              0.956 |         0.845 |
| …                       |                … |                  … |             … |
| tfidf-lognorm-df        |            0.826 |              0.857 |         0.878 |
| any-mention-is-relevant |            0.737 |              0.797 |         0.706 |

(46 documents / 15 topics scored — pairs in single-class groups are skipped.)

## Key findings

1. **IDF helps most where it's meant to: picking the top topics for a
   document.** On NDCG by document (threshold-free, the cleanest evidence) all
   four count/density TF-IDF variants beat their plain-TF baselines (0.928–0.939
   vs 0.919), `tfidf-density-cf` top at 0.939. The same ordering shows in
   by-document F1 (`tfidf-density-cf` 0.567 vs `mention-density` 0.546). The
   NDCG lift is ~0.02 — modest and near the small-sample noise band, but
   consistent across two independent metrics and all four variants, so more than
   a fluke.

2. **The win comes from per-group aggregation, not the pooled task.** Pooled
   (pointwise CV) F1 is a tie (0.585/0.580 vs 0.591); the gains appear only when
   averaging by document or by topic. That's exactly IDF's mechanism: it makes
   one global threshold separate relevant from not _consistently across topics
   of very different frequency_, which matters when each group is weighted
   equally but washes out when all pairs are pooled.

3. **The by-topic NDCG invariance prediction holds exactly.** Density variants
   all score 0.921 (== `mention-density`) on NDCG by topic and count variants
   all 0.878 (== `mention-count`): IDF, a per-topic constant, cannot reorder
   documents _within_ a topic. Confirms the metric behaves as designed — IDF's
   only ranking lever is cross-topic (by-document / global). (By-_topic F1_ does
   differ, because a single global threshold interacts with the IDF rescaling.)

4. **Density beats count as the TF term; log-dampening is harmful.** Density
   variants lead count on three-class F1 (0.585/0.580 vs 0.536/0.504 CV) and tie
   on by-document NDCG. `tfidf-lognorm-df` is worst on everything (0.303 CV F1,
   0.826 NDCG) — squashing the count throws away usable signal; drop it.

5. **Detection is easy; grading is hard.** Best binary F1 (relevant vs not) is
   **0.811** (`mention-count` / `mention-density`), far above the ~0.61
   three-class `F1(1&2)`. The unsolved part is the **marginal-vs-highly relevant
   (1 vs 2)** boundary; best class-1 F1 is only ~0.23.

6. **The "best" predictor depends on aggregation.** Pooled (pointwise) F1 ties
   `mention-density` and `tfidf-density-cf`; by document `tfidf-density-cf`
   leads; by topic `tfidf-density-df` leads. The density family (plain or
   TF-IDF) tops every view — the positional features no longer lead any. See the
   four leaderboards in PREDICTOR_METRICS.md.

## Recommendations

- **For the top-topics-per-document goal:** `tfidf-density-cf` (density ×
  inverse collection frequency). It tops NDCG by document (0.939 vs 0.919) and
  by-document F1 (0.567 vs 0.546), and ties `mention-density` pooled. The gain
  is small (~0.02) and the per-group F1s are optimistic, but it's consistent
  across metrics — the best bet when the output is a ranked topic list per
  document.
- **For a single pooled classifier:** `mention-density`
  `(low=0.0019, high=0.045)` is still the simplest equal-best — TF-IDF only
  pulls ahead per group.
- **Binary "relevant or not":** `mention-density` or `mention-count` (F1 ≈
  0.81).
- **Deprioritise / drop:** `tfidf-lognorm-df`, `max-section-density`,
  `first-fraction`, the 3/5/15-page variants, and the combination predictors —
  tried, do not improve on the best single feature.
- **Next steps to attack the 1-vs-2 boundary** (where everything plateaus near
  density ≈ 0.59 CV):
  1. **More labelled data** — 49 documents is small; class 1 is the weak spot,
     and it's also what limits confidence in the small TF-IDF by-document lift.
  2. **A learned combination** over the existing features (regularised logistic
     / ordinal regression, same grouped CV), now including the TF-IDF features.

## Reproducing

```sh
uv sync --extra research
# whole pipeline: build dataset (local Vespa + Snowflake local_dev) -> tune -> evaluate
just pipeline <eval.csv>
```

`evaluate_predictors.py` holds each predictor's tuned `(low, high)`. If
re-tuning shifts them, paste the new values from THRESHOLD_TUNING.md back in and
re-run `just evaluate`.
