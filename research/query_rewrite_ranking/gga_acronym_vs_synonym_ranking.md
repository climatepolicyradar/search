# Why "gga" and "global goal on adaptation" in ranking (rule rewrites)

See FUS-258. Written by Claude and human edited.

Searching `gga` in the `passage_search` debug CLI returns passages containing
the literal token "gga" ranked above passages containing the synonym phrase
"global goal on adaptation" — even though
[`passages.sr`](../../vespa/app/rules/passages.sr) has a rewrite rule connecting
the two. The rewrite doesn't remove "gga" from the query, so both forms stay
independently matchable.

## The rewrite is additive, not a replacement

The rule, in `vespa/app/rules/passages.sr`:

```text
gga +> ?"global goal adaptation";
```

`+>` means **LHS or RHS** (documented in the file's own header comment). The
query is rewritten to `gga OR "global goal adaptation"` — "gga" is never
dropped, it stays independently matchable alongside the phrase. A passage
containing only "gga" and no synonym text still matches, and matches on its own
bm25 score for that one token.

The RHS phrase also deliberately omits "on": `passages.sr` explains that
`passage_analysis` strips stopwords at index time, so an exact-phrase query that
spells one out doesn't match the resulting token positions, even against text
that verbatim contains it. "global goal on adaptation" (with "on") matched
nothing in testing; "global goal adaptation" matches correctly, including
passages that still say "...global goal on adaptation...".

## The rank profile

Passage search's default rank profile is `bm25_multiplicative`
(`vespa/app/schemas/passages.sd`, selected via `_DEFAULT_PASSAGE_RANK_PROFILE`
in `search/engines/dev_vespa.py`):

```text
function text_score() {
    expression: bm25(content)
}
function proximity_boost() {
    expression: 1 + query(prox_weight) * nativeProximity(content)
}
first-phase {
    expression: (text_score() * proximity_boost + topic_score()) * (1 - short_headings_penalty) * (1 - table_of_contents_penalty) * (1 - reference_list_penalty) * (1 - page_header_or_footer_penalty) * (1 - demoted_section_penalty)
}
```

There's no second-phase, no fieldMatch feature, and no phrase bonus beyond
`nativeProximity` scaled by `query(prox_weight) = 2.0`. So the synonym-expanded
phrase is scored identically to an organic query term — whatever happens next is
down to `bm25(content)` alone.

## The formula, from Vespa's own docs

```text
score(D,Q) = Σᵢ IDF(qᵢ) · f(qᵢ,D)·(k₁+1) / [f(qᵢ,D) + k₁·(1−b + b·fieldLen/avgFieldLen)]

IDF(qᵢ) = ln( 1 + (N − n(qᵢ) + 0.5) / (n(qᵢ) + 0.5) )
```

N is the number of passages on the content node; n(qᵢ) is how many contain query
term i; f(qᵢ,D) is how many times it occurs in this passage. `passages.sd` sets
`b = 0.4` and leaves k₁ at Vespa's default (1.2). Vespa computes IDF **per
content node**: "as the IDF is calculated per content node and index, slight
variations might occur." (Source:
[docs.vespa.ai/en/reference/bm25.html](https://docs.vespa.ai/en/reference/bm25.html))

`bm25(content)` sums this per query term across whatever terms matched — so the
question isn't "is gga rarer than 'global'?" (yes, trivially), it's "does gga's
one term-score beat the _sum_ of three term-scores from the phrase?"

## What the real corpus says

Querying the debug CLI with single words gets real document-frequency counts
across the production passage corpus (N ≈ 11,024,574 passages):

| term               | docs containing it | share of corpus |        IDF |
| ------------------ | -----------------: | --------------: | ---------: |
| `gga`              |         ≤ 1,363 \* |        ≤ 0.012% |      8.998 |
| `global`           |            411,335 |          3.731% |      3.288 |
| `goal`             |            238,120 |          2.160% |      3.835 |
| `adaptation`       |            498,557 |          4.523% |      3.096 |
| _sum of the three_ |                  — |               — | **10.220** |

\* upper bound — this is `total_count` for the rewritten query
`gga OR "global goal adaptation"`, since `gga` alone can't be queried without
the rewrite firing.

**Even at its upper bound, gga's IDF (8.998) is below the phrase's summed IDF
(10.220).** Rarer per term, yes — but BM25 doesn't compare term-to-term, it
compares one term's score against a sum of three. At matched term frequency and
field length, the phrase should score _higher_, not lower.

Modelling `f(qᵢ,D)·(k₁+1) / [f(qᵢ,D) + k₁·(1−b+b·ratio)]` at average field
length (`ratio = 1`) as each term repeats confirms the phrase stays ahead at
every repetition count, not just once:

| repeats | gga (1 term) | phrase (3 terms, summed) |
| ------: | -----------: | -----------------------: |
|      1× |        8.998 |                   10.220 |
|      2× |       12.372 |                   14.052 |
|      3× |       14.139 |                   16.060 |
|      4× |       15.227 |                   17.295 |
|      5× |       15.964 |                   18.132 |

This was confirmed directly against a real (local, isolated) Vespa instance, not
just the formula: feeding two length-matched synthetic passages — one containing
only "gga", one containing only "global goal adaptation", padded to the same
word count — and searching `gga` gave `bm25(content)` of **0.656** for the
acronym-only passage against **0.671** for the phrase-only passage. The phrase
won, exactly as the corpus math predicts. (Ad hoc measurement against
`tests/test_vespa_passages_e2e.py`'s local Vespa fixture — not a committed
test.)

## Scores

Two live `passage_search` runs against the production endpoint show what's
really happening.

**`query gga`** (rewrite fires: `gga OR "global goal adaptation"`), top hit:

```text
id       UNFCCC.non-party.1587.0::73
bm25(content)         21.964565542958013
fieldLength(content)  29.0
relevance             53.55213801070417   # first-phase score
```

**`query "global goal adaptation"`** typed literally (no "gga" in the query
text, so the rule never fires), top hit:

```text
id       UNFCCC.non-party.1121.0::32
bm25(content)         18.173672514150155
fieldLength(content)  114.0
relevance             43.9744532827754
```

The first passage wasn't acronym-only — it said "Global Goal on Adaptation
(GGA)" three times over, matching **both** branches of the rewrite's OR at once
and summing the score from all of it. It was also short (29 tokens against 114),
and Vespa's length normalization (`b = 0.4`) rewards the shorter field. Neither
factor is "rare beats common": one passage simply matched more query terms, and
Vespa's own normalization favoured its size. A genuinely acronym-only passage,
at typical length, isn't expected to outrank a phrase-only one — the isolated
same-length test above is the direct proof.

(Caveat: typing three bare words for the second query doesn't reproduce the
rule's `?"..."` phrase-adjacency requirement exactly — Vespa's simple query
syntax ORs/ANDs loose terms here rather than requiring them adjacent. It's real
production data, but not a perfectly isolated A/B; the length-matched local test
above is the clean isolation.)

## Census of the top 50

The two-example comparison above generalizes: pulling every result for `gga` up
to rank 50 (via `DevVespaPassageSearchEngine` directly, to get clean per-hit
`summaryfeatures` instead of the CLI's truncated text display and checking each
passage's raw text for the literal token vs. the three phrase words gives:

```text
  # id                               type               bm25   len      rel  gga  phrase  both   #gga
-----------------------------------------------------------------------------------------------------
  1 UNFCCC.non-party.1587.0::73      Text             21.965  29.0   53.552   Y      Y      Y       3
  2 UNFCCC.non-party.1588.0::121     Text             21.965  29.0   53.552   Y      Y      Y       3
  3 UNFCCC.non-party.1587.0::71      sectionHeading   21.243  13.0   51.792   Y      Y      Y       2
  4 UNFCCC.non-party.1588.0::119     sectionHeading   21.243  13.0   51.792   Y      Y      Y       2
  5 CCLW.party.1766.0::50            Text             22.209  46.0   46.885   Y      Y      Y       4
  6 UNFCCC.party.1766.0::50          Text             22.209  46.0   46.885   Y      Y      Y       4
  7 UNFCCC.non-party.1588.0::38      Text             21.931  70.0   46.304   Y      Y      Y       4
  8 UNFCCC.document.i00006937.n0000::184 Text             20.937  48.0   44.326   Y      Y      Y       3
  9 UNFCCC.party.1234.0::29          Text             20.675  81.0   44.116   Y      Y      Y       4
 10 UNFCCC.document.i00006937.n0000::183 Text             20.474  86.0   43.222   Y      Y      Y       4
 11 UNFCCC.party.1247.0::17          Text             19.107  87.0   42.634   Y      Y      Y       3
 12 CCLW.party.1769.0::58            Text             19.639  45.0   41.461   Y      Y      Y       3
 13 UNFCCC.party.1769.0::58          Text             19.639  45.0   41.461   Y      Y      Y       3
 14 UNFCCC.non-party.959.0::45       Text             19.621  71.0   41.422   Y      Y      Y       4
 15 UNFCCC.party.805.0::28           Text             19.272  52.0   40.686   Y      Y      Y       3
 16 CCLW.party.1786.0::129           List             19.257 105.0   40.654   Y      Y      Y       5
 17 UNFCCC.party.1786.0::129         List             19.257 105.0   40.654   Y      Y      Y       5
 18 UNFCCC.non-party.1588.0::125     Text             16.586  97.0    40.44   Y      Y      Y       2
 19 UNFCCC.non-party.1587.0::77      Text             16.586  97.0    40.44   Y      Y      Y       2
 20 UNFCCC.party.1839.0::7           Text             19.149  86.0   40.427   Y      Y      Y       3
 21 UNFCCC.non-party.1253.0::19      Text             18.774  62.0   39.633   Y      Y      Y       3
 22 UNFCCC.non-party.249.0::19       Text             18.774  62.0   39.633   Y      Y      Y       3
 23 UNFCCC.document.i00006511.n0000::104 Text             18.076  77.0    38.16   Y      Y      Y       3
 24 UNFCCC.document.i00006635.n0000::104 Text             18.076  77.0    38.16   Y      Y      Y       3
 25 UNFCCC.document.i00006539.n0000::183 Text             18.038  40.0    38.08   Y      Y      Y       2
 26 UNFCCC.non-party.1754.0::140     Text             17.987  79.0   37.972   Y      Y      Y       3
 27 UNFCCC.document.i00006937.n0000::185 Table            17.801 273.0   37.579   Y      Y      Y       9
 28 CCLW.document.i00006256.n0000::228 Text             17.446  50.0   36.831   Y      Y      Y       2
 29 UNFCCC.document.i00006644.n0000::63 Text             17.268  96.0   36.454   Y      Y      Y       3
 30 UNFCCC.document.i00000077.n0000::41 Text             17.031  87.0   35.954   Y      Y      Y       2
 31 UNFCCC.party.1851.0::16          Text             16.806  92.0   35.579   Y      Y      Y       2
 32 UNFCCC.document.i00006937.n0000::153 Text             16.787  62.0   35.439   Y      Y      Y       2
 33 UNFCCC.document.i00007946.n0000::149 footnote         16.772  26.0   35.408   Y      Y      Y       1
 34 UNFCCC.document.i00000536.n0000::780 sectionHeading   16.468  12.0   34.765   Y      Y      Y       1
 35 UNFCCC.document.i00000536.n0000::901 sectionHeading   16.468  12.0   34.765   Y      Y      Y       1
 36 UNFCCC.party.1784.0::61          List             16.216  15.0   34.233   Y      Y      Y       1
 37 CCLW.party.1784.0::55            List             16.216  15.0   34.233   Y      Y      Y       1
 38 UNFCCC.party.1768.0::14          List             15.878 178.0   33.882   Y      Y      Y       3
 39 CCLW.party.1768.0::14            List             15.878 178.0   33.882   Y      Y      Y       3
 40 UNFCCC.non-party.325.0::2        Text             16.031  77.0   33.843   Y      Y      Y       2
 41 UNFCCC.non-party.1854.0::63      Text             15.983  78.0   33.742   Y      Y      Y       2
 42 UNFCCC.document.i00006547.n0000::267 Text             15.936  79.0   33.642   Y      Y      Y       2
 43 UNFCCC.party.52.0::41            Text             15.748  83.0   33.246   Y      Y      Y       2
 44 UNFCCC.document.i00006937.n0000::25 Text             15.656  22.0   33.052   Y      Y      Y       1
 45 UNFCCC.document.i00000775.n0000::573 Text             15.656  85.0   33.051   Y      Y      Y       2
 46 UNFCCC.document.i00003849.n0000::573 Text             15.656  85.0   33.051   Y      Y      Y       2
 47 UNFCCC.non-party.1268.0::20      List             15.537 251.0     32.8   Y      Y      Y       4
 48 UNFCCC.non-party.1864.0::46      Text              15.52  88.0   32.764   Y      Y      Y       2
 49 UNFCCC.document.i00006729.n0000::141 Text              15.52  88.0   32.764   Y      Y      Y       2
 50 UNFCCC.party.1639.0::44          List             15.354  26.0   32.414   Y      Y      Y       1

gga-only: 0  phrase-only: 0  both: 50  neither: 0
```

Three things this census confirms:

- **Zero pure acronym-only or phrase-only passages appear in the top 50** —
  every hit matches both branches of the OR rewrite. Co-occurrence, not rarity,
  dominates the top of the ranking; this is exactly why the existing
  `acronym-gga` relevance test has to search `k=700` deep before it can find
  even one phrase-only passage.
- **bm25 alone doesn't determine order.** Rows 5–6 have a _higher_
  `bm25(content)` (22.209) than rows 1–4 (21.965, 21.243) but rank _lower_ on
  final `relevance` (46.885 vs 53.552) — `proximity_boost` and the junk-penalty
  multipliers in the `first-phase` expression are doing real work here, not just
  `bm25(content)`.
- **`#gga` (repetition count) falls as rank falls, but length compensates.**
  Rows 34–37, 44 and 50 match "gga" only once, yet still place in the top 50
  because they're very short (12–26 tokens — `sectionHeading`, `footnote`,
  `List`). Conversely, row 27 repeats "gga" nine times but only reaches rank 27,
  because its `fieldLength` is 273 tokens — length normalization outweighing raw
  repetition.
- The corpus also indexes near-duplicate submissions under multiple document IDs
  fairly often (the same passage text appears under both `UNFCCC.party.*` and
  `CCLW.party.*`, or `UNFCCC.non-party.*` variants) — visible as adjacent rank
  pairs with identical scores throughout the table.

## Pointers

- Rewrite rules:
  [`vespa/app/rules/passages.sr`](../../vespa/app/rules/passages.sr),
  [`vespa/app/rules/documents.sr`](../../vespa/app/rules/documents.sr) (included
  by `passages.sr`, holds shared acronym rules)
- Rank profile:
  [`vespa/app/schemas/passages.sd`](../../vespa/app/schemas/passages.sd)
  (`bm25_multiplicative`)
- Engine wiring: `search/engines/dev_vespa.py` — `"rules.rulebase": "passages"`,
  `_DEFAULT_PASSAGE_RANK_PROFILE = "bm25_multiplicative"`
- BM25/IDF formula reference:
  [docs.vespa.ai/en/reference/bm25.html](https://docs.vespa.ai/en/reference/bm25.html)
- Existing test coverage: `relevance_tests/test_passages.py` (case categorized
  `acronym-gga`), `tests/test_vespa_passages_e2e.py`
