# vespa-local

For when remote seems too far away.

A Vespa container, a corpus sampled from production, and a small k6 harness —
enough to point [api/](../../api/) at a local Vespa and measure search-api end
to end on one machine.

## Why this exists separately from [vespa/](../../vespa/)

`vespa/` is the day-to-day dev container: get some data in, poke at a query.
Performance testing needs something else — a corpus you chose, that stays put,
on an instance nothing else is writing to. So this is its own container
(`vespa-local`, ports 8082/19072), able to run alongside `vespa/`'s without
either one's data landing in the other. The Vespa application deployed is the
same one: [vespa/app](../../vespa/app).

## Quickstart

```bash
cd search/vespa-local

just all          # gen-documents -> up -> deploy -> feed-documents
just serve-api    # terminal 1
just perf-test    # terminal 2
```

`just` on its own lists every recipe.

Requires Docker, [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/)
(`brew install k6`), and AWS credentials for the production account — the corpus
comes from a prod bucket, so `gen-documents` assumes `AWS_PROFILE=production`
unless you set it to something else.

## The corpus

`just gen-documents` samples
`s3://cpr-prod-snowflake-data-export/production/published/pipeline_data_in_vespa_documents_updates_v1/`
— the same export the `search-vespa-feeder-documents` Prefect flow feeds — into
`.data_cache/vespa-local/documents.jsonl`, with a `manifest.json` next to it
recording exactly what was sampled.

Two slices, both load-bearing:

| slice   | flag              | what it is                                                                                                          |
| ------- | ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| largest | `--largest` (200) | the documents with the biggest `passages` arrays — the expensive ones, and the reason for doing this locally at all |
| stride  | `--every` (5)     | every Nth document scanned — ordinary documents, so that filters and facets have something to match                 |

Without the second slice the first is unmeasurable: the queries in `perf.ts`
filter on `category::Report`, `status::Principal` and ask for facet counts, and
against a corpus of nothing but outliers they would all return zero hits and
time an empty result set.

Three things worth knowing:

- It samples an **immutable timestamped snapshot**, not `latest/`. `latest/` is
  rewritten in place over several minutes, so a read that straddles a publish
  mixes part files from two different exports. `manifest.json` records which
  snapshot was used — pass it back as `--snapshot` to rebuild the same corpus.
- It applies the **same derivations the production feeder applies**
  (`derive_document_data`, imported from `vespa-feeder/documents_flow.py`), so
  locally fed documents have the `id` and `principal_id` that production
  documents have.
- `--files` defaults to 32 of the ~640 part files (~0.5GB downloaded, streamed,
  never landed on disk). `--files all` gets the real tail, at ~11GB.

## The perf test

`just perf-test` runs five `/search/documents` shapes, each taken from the
existing suite in [k6/](../../k6/) rather than invented, so a local number is
measuring the same request production measures:

| shape            | source                                 | what it costs                                                                       |
| ---------------- | -------------------------------------- | ----------------------------------------------------------------------------------- |
| `fan-out`        | `k6/tests/breakpoint/load.ts`          | both facet fields plus filters — up to 8 concurrent Vespa queries per request       |
| `nested-filters` | `documents/filter-combinations.ts`     | the nested or-in-and shape navigator-frontend sends                                 |
| `order-by`       | `documents/order-by-combinations.ts`   | sorting by attribute rather than relevance                                          |
| `deep-page`      | `documents/pagination-combinations.ts` | offset 490 — Vespa skipping ranked hits                                             |
| `large-page`     | `documents/pagination-combinations.ts` | 100 hits of summaries, which is what the large-`passages` corpus is there to stress |

Output is one table — per-shape request count, median, p95 and max, then overall
throughput and failure rate. VUs and duration are positional recipe arguments —
`just perf-test 20 2m` for 20 VUs over two minutes.

Only `/search/documents` is covered, because `feed-documents` feeds the
`documents` schema; `/search/passages` and `/search/labels` would be querying
empty content clusters. Adding them means adding a feed for their schemas first.

Two caveats on reading the numbers:

- A local corpus is three orders of magnitude smaller than production, so
  absolute latencies are not production latencies. What this is good for is
  **relative** movement — this branch against `main`, one ranking profile
  against another, one schema change against its predecessor.
- `deep-page` asks for offset 490. On a corpus of a few hundred documents that
  page is usually empty. It still exercises the offset path and still times it;
  it just is not returning anything.

Pin `VESPA_VERSION` (e.g. `VESPA_VERSION=8.585.35 just up`) if you are comparing
runs across days — `latest` moves, and a Vespa upgrade between two runs looks
exactly like a regression.
