# Labels route load-test coverage — 2026-09-16

FUS-340: load-test coverage for the search-api label routes, completing coverage
across all three route families (documents, passages, labels).

This is not a new breakpoint run — `/search/labels` was already one of the four
routes measured directly in both prior breakpoint runs
([2026-09-09](2026-09-09-breakpoint-test-baseline.md),
[2026-09-10](2026-09-10-breakpoint-test-baseline.md)); it just had no k6
smoke/load script to cite that data against. This file records what changed: new
scripts added, the `order_by` finding, and the `all_label_types()` flag.

## Scripts added

`k6/tests/smoke-load/routes/labels/`:

- `index.ts` — base query, default order. Smoke only.
- `filter-combinations.ts` — `type` param (unique to this route) and `filters`,
  individually and combined, plus a zero-result combination. Fixtures sourced
  from real navigator-frontend usage (`src/hooks/useLabelSearch.ts`,
  `src/pages/_search/index.tsx`, `src/pages/geographies/[id].tsx`), not guessed.
  Smoke + graduated `load` profile (see Thresholds below).
- `order-by-noop.ts` — regression guard, not a sweep of sortable fields (see
  Findings below). Smoke only.
- `pagination-combinations.ts` — first page, a deep page, a large `page_size`
  (navigator-frontend always requests `page_size=10000` in one shot rather than
  paging). Smoke only.

`k6/tests/smoke-load/routes/labels-taxonomy/`:

- `index.ts` — smoke only, no `load` profile. See Scope below for why this route
  is covered at all.

## Findings

### `order_by` has no effect on `/search/labels`

FUS-354 asked to confirm sortable `order_by` fields for this route against the
engine code, the way `documents/order-by-combinations.ts` and
`passages/order-by-combinations.ts` do for theirs. There are none to confirm:

- `api/routers.py`'s `read_labels` accepts and parses any
  `order_by=<field> <direction>` string via the shared generic dependency — no
  per-route field enum, unlike documents/passages, so a nonsense `order_by`
  value parses successfully rather than being rejected.
- `DevVespaLabelSearchEngine.search()` (`search/engines/dev_vespa.py`) takes
  `order_by: list[OrderBy]` annotated `# noqa: ARG002` — an explicit
  unused-argument lint suppression — and never references it in the method body.
  The Vespa request always hardcodes `"ranking.profile": "nativerank"` with no
  sort override.

Confirmed with search-api's owning team
([#team-fusion, 2026-09-16](https://climate-policy-radar.slack.com/archives/C09R5D5KCRK/p1789570989839129),
James Gorrie): deliberate/known, not a bug — the parameter only exists because
`DevVespaLabelSearchEngine` implements the abstract `SearchEngine.search()`
signature (`search/engines/__init__.py`), which requires it for
documents/passages; labels never wired up an implementation.

Rather than an `order-by-combinations.ts` sweep, `order-by-noop.ts` asserts two
different `order_by` values return identical result order — a regression guard,
not a sorting test. Verified live against production during this work:
`order_by=relevance asc` and the default both returned the same 50-result order,
byte-for-byte.

### `all_label_types()` — still called, still discarded, not resolved by this story

`api/routers.py:264` calls `engine.all_label_types()` after every
`/search/labels` request (marked `# NOTE: Is this still being used?` in the
code) but never uses the return value — confirmed by reading the full
`read_labels` handler: the result isn't assigned, logged, or returned.

**Not resolved as part of this story.** This ticket's scope is load-test
coverage, not fixing search-api routing logic — flagging it here per the
Definition of Done ("a note on whether `all_label_types()` is confirmed still
needed") rather than removing the call. If confirmed dead, it should be a
separate small cleanup PR (it's an extra unconditional Vespa call on every
`/search/labels` request, so removing it would be a small latency win, not just
tidiness).

## Scope: `/search/labels-taxonomy` included, despite the ticket's Won't-Have

The original ticket text excluded `/search/labels-taxonomy` from coverage. It's
actually live product surface: navigator-frontend calls it directly
(`src/hooks/useLabelSearch.ts`'s `loadLabelTaxonomy`) and merges its results
with `/search/labels` to build the sidebar filter tree
(`src/pages/_search/index.tsx`) — a temporary workaround for a data-lake
taxonomy issue (linked from that file: APP-2266), not dead code. Given that,
it's covered here with a smoke test.

Deliberately **smoke-only, no `load` profile**: `read_labels_taxonomy()`
(`api/routers.py`) returns a hardcoded in-memory Python list
(`api/labels_taxonomy.py`, ~56 entries at time of writing) with no Vespa call
and no I/O at all. There's no meaningful capacity ceiling to find here beyond
FastAPI/ASGI's own baseline throughput, already characterised by the
documents/passages/labels breakpoint runs. A regression here would be a code
change breaking serialisation or the hardcoded list itself — smoke coverage is
what catches that.

`/search/test_labels` remains excluded, per the ticket — confirmed unused
anywhere in navigator-frontend.

## Thresholds

`labels/filter-combinations.ts`'s `load` profile uses `p(95)<2000`,
`http_req_failed rate<0.01` (`abortOnFail: true`) — identical to the
documents/passages `load` profiles, and directly backed by the same two
breakpoint runs rather than borrowed:

| run                                                                    | labels p95 (healthy) | labels p95 (collapse) | offered rps at collapse |
| ---------------------------------------------------------------------- | -------------------- | --------------------- | ----------------------- |
| [2026-09-09](2026-09-09-breakpoint-test-baseline.md) (ECS min=1/max=4) | 960ms – 1.4s         | 1m0s (timeout)        | ~6rps                   |
| [2026-09-10](2026-09-10-breakpoint-test-baseline.md) (ECS min=3/max=8) | 860ms – 1.87s        | 20s+ – 1m0s (timeout) | ~9rps                   |

2000ms sits comfortably above the measured healthy region in both runs and well
below the collapse values — same reasoning the documents/passages threshold
comment already gives, now confirmed to hold for labels specifically rather than
assumed to carry over.

`documents/{document_id}/index.ts`, `passages/index.ts`, and
`passages/filter-combinations.ts`'s citation comments already point at these two
files; `labels/filter-combinations.ts` now joins them with the same citation,
since it's citing the same underlying measurements.

## Acceptance criteria (FUS-340)

1. ✅ Smoke test for `GET /search/labels`, base query + default order —
   `index.ts`
2. ✅ Smoke test covering `type` and `filters`, individually and together —
   `filter-combinations.ts`
3. ✅ `order_by` confirmed against the engine code — confirmed as a no-op, not a
   set of sortable fields; `order-by-noop.ts` covers it as a regression guard
4. ✅ Smoke test covering pagination — `pagination-combinations.ts`
5. ✅ `filter-combinations.ts` graduated in place to a load profile with
   documented thresholds, retaining `-e PROFILE=smoke`
6. Won't-have re-scoped: `/search/labels-taxonomy` is covered (smoke only, see
   Scope above) since it's actually used by the frontend; `/search/test_labels`
   remains excluded as originally scoped

## Verification

All six new scripts run clean locally against production
(`k6 run -e PROFILE=smoke`, 100% checks passing):

- `labels/index.ts` — 885/885 checks
- `labels/filter-combinations.ts` — 885/885 checks (5 combinations)
- `labels/order-by-noop.ts` — 174/174 checks
- `labels/pagination-combinations.ts` — 693/693 checks
- `labels-taxonomy/index.ts` — 360/360 checks

`labels/filter-combinations.ts`'s `load` profile was launched and confirmed to
parse/execute correctly (ramping-vus scenario, 50 max VUs) but not run to
completion as part of this work — sustained load runs are a separate,
explicitly-confirmed action per the k6-breakpoint-test skill, and this story's
threshold is already backed by the two prior full breakpoint runs rather than
needing a fresh one.
