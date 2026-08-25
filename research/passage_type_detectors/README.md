# Passage type heuristics — validation sets

Claude-labelled evaluation data and lightweight eval script for two passage-type
heuristics in `search/passage.py`: `looks_like_table_of_contents`,
`looks_like_reference_list`, and `looks_like_demoted_section`.

```bash
uv run python research/passage_detectors/evaluate.py
```

Fields:

| Field                                         | Meaning                                                              |
| --------------------------------------------- | -------------------------------------------------------------------- |
| `id`, `document_id`, `content_type`, `corpus` | provenance, straight from Snowflake                                  |
| `content`                                     | the passage text, exactly as the detector sees it                    |
| `label`                                       | `1` if the passage IS the thing the detector hunts, else `0`         |
| `ambiguous`                                   | `true` where a careful reviewer could reasonably score it either way |
| `note`                                        | Claude reasoning about why it was labelled that way                  |
| `stratum`                                     | how the row was sampled (see below)                                  |
| `min_page`                                    | lowest PDF page the passage appears on                               |
| `n`, `n_lines`                                | TOC set only: row index and non-empty line count                     |
| `heading_text`                                | demoted-section set only: the section heading the passage sits under |
| `heading_content_type`                        | demoted-section set only: `sectionHeading`, `title`, or `pageHeader` |
| `n_passages_below`                            | demoted-section set only: how many passages this is heading for      |

## How to use (for agents)

### Strata, and which ones you must not compare across

The two files have **disjoint** stratum vocabularies, so per-stratum numbers are
not comparable between detectors.

Two strata need care:

**`fresh_firing` (TOC set, 40 rows) was sampled from one rule's own positives.**
It was drawn by running a candidate rule over a fresh corpus sample and
labelling what it fired on, so it measures _that_ rule's precision. It **cannot
be used to compare two detectors**: a rival's false positives are absent from it
by construction. This is a real trap — a boolean rewrite of the TOC rule looked
strictly better than the scored version largely because it was scored on this
slice.

**`fresh_disagreement` (both sets) is adversarially selected.** These are rows
from a fresh 5,995-passage draw where two candidate rules disagreed, labelled
afterwards. Every row is by definition one that at least one rule gets wrong, so
a low score here is expected and is a lower bound, not a fair standalone
measure. The shipped reference-list rule scores 0.000/0.000 on this slice for
exactly that reason. Read it as "here are the hard cases", not as a headline.

**Use `original strata only` for a like-for-like comparison against history.**
That slice reproduces the numbers the detectors were developed against.

### How to compare two candidate rules cheaply

This is the method that caught a wrong conclusion, and it is worth reusing:

1. Draw a fresh sample of passages from Snowflake that is in neither validation
   set.
2. Run both candidate rules over all of them.
3. Hand-label **only the rows where they disagree** — everything else is
   uninformative.

5,995 passages produced 19 TOC disagreements and 99 reference-list
disagreements. The 19 plus the first 22 of the 99 are the `fresh_disagreement`
rows here. Labelling ~20 passages is an afternoon; it settled a question the
566-row sets had answered wrongly.

### Baselines

Measured against the detectors as committed, on the `original strata only` slice
so the numbers are comparable to the development history:

| Detector                                                            | Slice                     |     P |     R |    F1 |
| ------------------------------------------------------------------- | ------------------------- | ----: | ----: | ----: |
| `looks_like_table_of_contents`, with `min_page` (as search runs it) | original strata           | 1.000 | 0.725 | 0.840 |
| "                                                                   | excl. ambiguous, all rows | 0.981 | 0.812 | 0.889 |
| `looks_like_table_of_contents`, text only                           | original strata           | 0.935 | 0.841 | 0.885 |
| `looks_like_reference_list`                                         | original strata           | 1.000 | 0.828 | 0.906 |
| "                                                                   | excl. ambiguous, all rows | 0.959 | 0.875 | 0.915 |
| `looks_like_demoted_section`, max 6 words                           | original strata           | 1.000 | 0.732 | 0.845 |
| `looks_like_demoted_section`, max 10 words                          | original strata           | 0.948 | 0.866 | 0.905 |

For scale, the rules these replaced, on the same TOC/reference-list rows: the
previous TOC rule scored P=0.328 / R=0.565 and fired on **50.2%** of all
multi-line passages in the corpus; the previous reference-list rule scored
P=0.925 / R=0.713.

The gap between the two TOC rows is the page veto: it takes precision from 0.935
to 1.000 and costs recall, because it rejects the per-chapter contents listings
that appear deep in long reports. That was a deliberate trade - a false positive
makes a relevance assertion pass vacuously, which is the failure mode that left
the `tables_of_contents` relevance cases unfalsifiable for months.

There is deliberately **no positional condition on the reference-list rule**:
reference lists sit at a median 0.62 of the way through their document against
0.55 for everything else, i.e. no signal, because numbered footnote citations
appear on every page rather than only at the end. `min_page` is in that file so
this stays checkable.

## Caveats

- **Single annotator, no adjudication.** The `ambiguous` flag marks the rows
  that deserve a second opinion; metrics are reported with and without them.
- **One duplicate.** The TOC set contains one passage twice (`n=97` and
  `n=176`), drawn into two different strata. Both copies carry the same label,
  and both are kept so row counts stay comparable with the numbers quoted above.
- **Sampling is stratified, not representative.** The strata were chosen to
  surface edge cases, so the positive rate here says nothing about the corpus
  positive rate. For corpus-level behaviour measure the firing rate on a random
  draw instead — that is how the 50.2% figure above was obtained.
- **Labels reflect the rules' purpose**, which is filtering junk out of
  relevance-test results. They are not a general-purpose document-structure
  ground truth.
- **The demoted-section set is heading-grain.** Its 300 rows stand for 300
  sections, not 300 passages, and `n_passages_below` records the fan-out.
  Nothing here measures whether the representative passage was typical of its
  section.
