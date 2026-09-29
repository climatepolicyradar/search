# Acronym candidates for query expansion

`vespa/app/rules/documents.sr` holds 11 hand-written acronyms. This folder finds
the rest, so a human can review them and add the good ones.

Nothing here writes to Snowflake or edits the `.sr` files. The output is a
spreadsheet you make decisions in.

## Run it

```bash
# everything, ~15 seconds
uv run --group research python research/acronyms/run.py
```

Or one step at a time:

| Step | Command           | Reads                 | Writes                                           |
| ---- | ----------------- | --------------------- | ------------------------------------------------ |
| 1    | `run.py fetch`    | Snowflake corpus      | `title_candidates.tsv`, `passage_candidates.tsv` |
| 2    | `run.py evidence` | Snowflake search logs | `search_evidence.json`                           |
| 3    | `run.py workbook` | the files above       | `acronym_candidates.xlsx`                        |
| 4    | `run.py sheets`   | the files above       | `acronym_candidates_sheets.csv`                  |
| 5    | `run.py notion`   | the files above       | `acronym_candidates_notion.csv`                  |

Steps 3 to 5 are three formats of the same list. Pick the one matching where the
review happens; you do not need all three.

`fetch` and `evidence` need the `local_dev` Snowflake profile (see
`research/document_topic_relevance/src/snowflake_client.py`) and open a browser
for SSO. The rest are offline and rebuild from `data/` in a couple of seconds.

**Collision screening needs the `knowledge-graph` repo checked out next to this
one**, for `../knowledge-graph/data/raw/geography-iso-3166.csv`. Without it the
country-code screen is off. You get a warning on stderr, and candidates that
should have been flagged (`br` is Brunei) come through clean.

`mine_acronyms.py` is the matcher, not run directly. Check it with:

```bash
uv run python research/acronyms/mine_acronyms.py --self-test
```

It asserts the matcher reproduces rules already in `documents.sr` (`tcfd`,
`necp`, `csrd`) and rejects years and jurisdictions (`(2021)`, `(EU)`).

## What each step does

**`fetch`.** Documents define their own acronyms: _"...Financial Disclosures
(TCFD)..."_. Two sources:

| Source                                  | Rows       | Size    |
| --------------------------------------- | ---------- | ------- |
| `PRODUCTION.PUBLISHED.DOCUMENTS.TITLE`  | 64,386     | 0.23 GB |
| `PRODUCTION.PUBLISHED.PASSAGES_V1.TEXT` | 77,822,999 | 8.67 GB |

Both scan in seconds on the X-Small warehouse. The passage query extracts and
groups matches **inside Snowflake** rather than selecting `TEXT`: 21% of
passages contain something bracketed, so pulling them raw would mean ~13 GB over
the wire.

The table is `PASSAGES_V1`. `PIPELINE_PASSAGES_V1`, used in
`research/document_topic_relevance`, is not visible to the
`PRODUCTION_PLAYGROUND` role.

**`evidence`.** Checks each acronym against `ANALYTICS_SEARCH_TERM_FIRST_SEEN`:
83,628 distinct search terms, Sept 2023 onwards. This separates "exists in our
documents" from "users actually type it". Only counts are stored, no raw
queries.

Do not substitute `ANALYTICS_POSTHOG_EVENTS_PRODUCTION.SEARCH_QUERY`. That
column only started filling in Sept 2026 (FUS-228) and held 39 terms when
checked.

**`workbook`.** One row per acronym, split over two sheets: _Review these_ (526
rows) and _Suggested no_ (980 rows, in our documents but unevidenced). A
`Yes / Maybe / No` dropdown pre-filled with a suggestion, and a column saying
why, so you can disagree knowingly.

**`sheets`.** The same seventeen columns as one CSV for Google Sheets. Filter
`DECISION <> No` to get the _Review these_ sheet back. A CSV cannot carry a
dropdown or conditional formatting, so the command prints the clicks that
restore them.

`--review-only` drops the suggested-No rows, leaving 526 instead of 1,506:

```bash
uv run --group research python research/acronyms/run.py sheets --review-only
```

A No means no search evidence since Sept 2023, not a wrong acronym. All 980 are
in our documents. Rerun without the flag to get them back.

**`notion`.** Ten columns instead of seventeen, shaped for a Notion import, with
a plain-English "what to check" per row.

## How a candidate is judged

The acronym's letters must appear **in order** among the initials of the
preceding words. Letters may be skipped: `TCFD` omits the "Force" in _Task Force
on Climate-related Financial Disclosures_.

That check is what makes the output usable. Brackets also hold years,
jurisdictions and table cells. On 1,086 sampled passages a naive bracket pattern
matched 12 blocks, 11 of them ordinary two-column tables ("Foundry | Ceramic").
The initials check left the one real glossary.

Then two more steps:

- **Stopwords are stripped from the expansion.** `"global goal on adaptation"`
  matches nothing once indexed; `"global goal adaptation"` matches correctly,
  including text that says "on". See `vespa/app/lucene-linguistics/README.md`.
- **Collisions are screened** against ISO country codes, `en/geo-synonyms.txt`
  and the existing `.sr` rules. The automated form of the `nz` (New Zealand /
  net zero) problem.

## Reading the output

| Group              | Meaning                                                                |
| ------------------ | ---------------------------------------------------------------------- |
| 1 Best picks       | In document text, no known clash. Start here.                          |
| 2 Clash or unclear | Collides with a country code, already a rule, or has several meanings. |
| 3 Two letters      | Recommend skipping all of them.                                        |
| 4 Only in titles   | In document titles but never in body text.                             |

Only group 1 is ever suggested `Yes`. Groups 2 and 3 are capped at `Maybe`
however often they are searched. `br` is still Brunei.

**"No clash detected" is not "safe to ship."** The screen knows geography and
the existing rules, and only partly knows ordinary English. `bat`, `arc` and
`api` all sit in group 1. Read every line.

**Everyday words are screened in two passes.** The curated `AMBIGUOUS` list in
`run.py` is what downgrades a suggestion to `Maybe`. CITES is the cautionary
entry: a real treaty acronym that is also the ordinary verb "cites", which sat
in `Yes` claiming "not an everyday word" until someone read the line.

The second pass checks `/usr/share/dict/words` but only writes a warning. It
does not decide, because the list is unabridged: it also holds `guan`, `kea`,
`nid` and `ria`, and letting it vote demoted real acronyms. A dictionary hit
means a human should look. When you confirm one is genuinely everyday, add it to
`AMBIGUOUS`. Without the word list the pass is skipped with a warning and the
curated list still applies.

Three more traps:

- **Frequency is not importance.** `ara` ("amendment restatement agreement")
  ranks near the top on count alone, but it is legal boilerplate repeated within
  a few documents.
- **"User typed the long name" is the weakest column.** Court case names from
  climatecasechart.com inflate it; every hit for `carb` was a variant of _"exxon
  v california air resources board"_. It argues for a reverse rule
  (`long form -> ?acronym`, as `passages.sr` does for `nature based solution`)
  rather than the one in the "Rule to paste" column.
- **"No" under search evidence means no evidence, not never.** Nothing before
  Sept 2023 is visible.

## Files

| Path                        | What                                                       |
| --------------------------- | ---------------------------------------------------------- |
| `mine_acronyms.py`          | the matcher: extraction, validation, collision screening   |
| `run.py`                    | the pipeline, all five steps                               |
| `data/*.tsv`                | candidates, one row each, with a ready-to-paste rule line  |
| `data/search_evidence.json` | per-acronym search signals                                 |
| `data/unterm.json`          | UN terminology cross-check; steps 3 to 5 use it if present |

The three review files are not kept here. They are pure output: rebuild any of
them in seconds with `run.py workbook`, `sheets` or `notion`, no Snowflake
needed. Once you record decisions in one it stops being regenerable, so keep
that copy wherever the review happens.

`unterm.json` is the exception. Nothing in this folder fetches it, so if it is
deleted it does not come back. The UNTERM columns go blank if it is missing.
