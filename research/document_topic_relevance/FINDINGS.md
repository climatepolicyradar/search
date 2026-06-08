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
per-page passage counts. Topics join to the warehouse on `Label.value` ↔
`TOPIC_NAME`.

## Methodology

- **Predictors** are `ThresholdPredictor`s: each computes one continuous feature
  and maps it to `{0,1,2}` via two thresholds (`low`, `high`). A predictor
  returns `0` whenever the topic isn't mentioned at all.
- **Thresholds are tuned** by grid search over feature quantiles, with
  **document-grouped cross-validation** (whole documents held out per fold) so
  thresholds don't peek at the documents they're scored on. Objective =
  **macro-F1 over classes 1 & 2** (class 0 ignored). The honest number is the CV
  mean; the full-set fit is optimistic.
- **Caveat throughout:** with only 49 documents, treat differences under
  ~0.02–0.03 F1 as noise.

## Headline results

Tuned, document-grouped cross-validated F1 on classes 1 & 2 (the number to
trust):

| Predictor              | CV F1(1&2) | tuned (low, high) | feature                                   |
| ---------------------- | ---------: | ----------------- | ----------------------------------------- |
| **mention-density**    |  **0.591** | (0.0019, 0.045)   | mentions ÷ total passages                 |
| decay-weighted         |      0.573 | (1.98, 97.4)      | mentions weighted by 1/position decay     |
| first-10-pages         |      0.572 | (0, 7)            | # mentions in first 10 pages              |
| first-10-pages-density |      0.566 | (0, 0.016)        | mention density within first 10 pages     |
| first-5-pages          |      0.558 | (0, 3)            | # mentions in first 5 pages               |
| mention-count          |      0.550 | (3.7, 309)        | raw # mention passages                    |
| max-mentions-per-page  |      0.539 | (2, 11.2)         | peak mentions on any page                 |
| first-15-pages         |      0.533 | (0, 11)           | # mentions in first 15 pages              |
| earliest-mention-page  |      0.517 | (2, 43.2)         | page of earliest mention (smaller better) |
| first-fraction         |      0.476 | (1.5, 16)         | # mentions in first 15% of passages       |
| earliest-mention       |      0.460 | (0.38, 0.99)      | earliness = 1 − first_idx/total           |
| first-3-pages          |      0.455 | (0, 1)            | # mentions in first 3 pages               |
| max-section-density    |      0.446 | (0.091, 1)        | peak mention density within a section     |

Combination predictors (fuzzy AND/OR over the above, not separately tuned) did
**not** beat the best single predictor: `(count or density) and early` = 0.574
full-set, `density and early` = 0.547 full-set, both below `mention-density`.

## Key findings

1. **`mention-density` is the predictor to ship.** It's the most consistent
   winner — #1 pointwise (0.591 CV / 0.615 full), #1 by-document (0.546), #2
   by-topic (0.510), and tied #1 on binary detection (0.811). Simple and
   interpretable.

2. **Detection is easy; grading is hard.** Collapsing 1 & 2 into one "relevant"
   class vs 0, the best binary F1 is **0.811** (`mention-count` /
   `mention-density`) — far above the ~0.61 three-class `F1(1&2)`. The unsolved
   part is the **marginal-vs-highly relevant (1 vs 2)** boundary; best class-1
   F1 is only ~0.23.

3. **Filtering weak mentions is what wins detection.** Every positional
   predictor with `low = 0` collapses to exactly the baseline on the binary task
   (P 0.541 / R 0.990 / F1 0.699) — they predict "relevant" for _any_ mention.
   `mention-count` and `mention-density` have a real lower threshold, rejecting
   weak mentions for +0.18 precision at almost no recall cost (binary F1 0.699 →
   0.811).

4. **Sub-region density never beats whole-document density.** Every
   length-normalised _slice_ measure underperforms plain `mention-density`
   pointwise: per-section (0.446), first-fraction (0.476), first-n-pages-density
   (0.566). Normalising over a slice adds noise on this small set.

5. **The positional window peaks at ~10 pages.** first-3 (0.455) < first-5
   (0.558) < first-10 (0.572) > first-15 (0.533) — wider windows dilute the
   "early ⇒ relevant" signal.

6. **The "best" predictor depends on aggregation.** Pointwise and by-document
   favour `mention-density`; **by-topic** (equal weight per topic) puts
   `first-10-pages-density` narrowly first — it's more even across topics rather
   than carried by high-frequency ones. See the four leaderboards in
   PREDICTOR_METRICS.md.

7. **Tuning matters most for class-1 recall.** Moving from hand-picked to tuned
   thresholds lifted `mention-density`'s class-1 recall from 0.225 → 0.736.

## Recommendations

- **Primary:** `mention-density` with tuned thresholds
  `(low=0.0019, high=0.045)`.
- **Binary "relevant or not":** `mention-density` or `mention-count` (F1 ≈ 0.81)
- **Topic-robustness (equal weight per topic):** consider
  `first-10-pages-density`.
- **Deprioritise:** `max-section-density`, `first-fraction`, the 3/5/15-page
  variants, and the combination predictors — tried, do not improve on the best
  single feature.
- **Biggest expected gains are no longer in hand-crafted features** (the space
  is explored and plateaued near density ≈ 0.59 CV). Highest-leverage next
  steps:
  1. **More labelled data** — 49 documents is small; class 1 is the weak spot.
  2. **A learned combination** over the existing features (regularised logistic
     / ordinal regression, evaluated with the same grouped CV) to attack the
     1-vs-2 boundary.

## Reproducing

```sh
uv sync --extra research
# 1. build the enriched dataset (Vespa local + Snowflake local_dev)
uv run python load_dataset.py <eval.csv>
# 2. evaluate all predictors -> PREDICTOR_METRICS.md
uv run python evaluate_predictors.py
# 3. tune thresholds (grouped CV) -> THRESHOLD_TUNING.md + data/threshold_tuning.csv
uv run python tune_thresholds.py
```
