# k6 scripts

Smoke and load tests for search-api, written in TypeScript. k6 transpiles `.ts`
files internally (via esbuild) at run time — the k6 binary alone is enough to
run these scripts.

Node/npm are only needed for type-checking (`@types/k6`, `tsconfig.json`) — not
for running the scripts themselves.

## Install

```bash
brew install k6
```

Requires k6 v0.57+ for TypeScript support (Homebrew's current formula is well
above this).

To type-check the scripts, also run `npm install` from this directory.

Commands below assume you're already in this directory (`cd k6`) — paths are
relative to here, not the repo root.

## Layout

One directory per search-api route under `routes/`, mirroring the route's URL
path. Each route directory holds one file per test concern (named after what it
tests, not "smoke"/"load") plus its own `fixtures/`. The base case for a route
is `index.ts`:

```text
k6/
  config.ts                    # shared BASE_URL / PROFILE resolution
  routes/
    documents/
      index.ts                # GET /search/documents (base query)
      filter-combinations.ts  # GET /search/documents?filters=
      order-by-combinations.ts # GET /search/documents?order_by=
      fields-combinations.ts  # GET /search/documents?fields=
      pagination-combinations.ts # GET /search/documents?page_token/page_size
      fixtures/
        search-queries.json        # realistic free-text search terms
        order-by-combinations.json # all sortable field/direction combinations
        filter-combinations.json   # real filters shapes, see note below
      {document_id}/
        index.ts               # GET /search/documents/{document_id}
        fixtures/
          document-ids.json    # real, pre-verified document_ids
    passages/
      index.ts                # GET /search/passages (base query)
      filter-combinations.ts  # GET /search/passages?filters=
      order-by-combinations.ts # GET /search/passages?order_by=
      pagination-combinations.ts # GET /search/passages?page_token/page_size
      fixtures/
        search-queries.json        # realistic free-text search terms
        filter-combinations.json   # real filters shapes, see note below
        order-by-combinations.json # all sortable field/direction combinations
        pagination-combinations.json # page_token/page_size combinations
```

Every file in a route directory tests that one route — co-locating them means
you can see all the ways a route is exercised in one place, and the directory
structure traces back directly to the FastAPI route tree. Splitting further by
test concern (rather than one file per route) keeps each file small,
single-purpose, and runnable in isolation.

## Running

```bash
k6 run routes/documents/index.ts
k6 run "routes/documents/{document_id}/index.ts"
k6 run routes/documents/order-by-combinations.ts
k6 run routes/documents/filter-combinations.ts
```

Defaults to hitting production (`https://api.climatepolicyradar.org/search`).
Override with `BASE_URL`:

```bash
BASE_URL=https://staging.example.com/search k6 run routes/documents/index.ts
```

## Smoke vs. load: one file, one `PROFILE`

Each script exports a `PROFILES` map and picks one via `-e PROFILE=<name>`
(defaulting to `smoke` if unset), rather than duplicating the request logic
across separate smoke/load files. `resolveProfile` also takes a route-qualified
cloud name (e.g. `"documents/{document_id}: base query"`), set as
`options.cloud.name` — this is what Grafana Cloud k6 groups a script's runs
under; without it, Cloud falls back to the script's own filename, and multiple
routes following the `index.ts` base-case convention (see Layout above) would
otherwise collide under one indistinguishable "index.ts" name in the project's
runs list:

```bash
k6 run routes/documents/index.ts               # smoke (default)
k6 run -e PROFILE=smoke routes/documents/index.ts
k6 run -e PROFILE=load "routes/documents/{document_id}/index.ts"
k6 run -e PROFILE=load routes/documents/fields-combinations.ts
k6 run -e PROFILE=load routes/passages/index.ts
k6 run -e PROFILE=load routes/passages/filter-combinations.ts
```

The `smoke` profile is low VUs (2-5), short duration (~1min), checking for zero
failed checks — see k6's
[smoke testing guide](https://grafana.com/docs/k6/latest/testing-guides/test-types/smoke-testing/).
Every script has one. A `load` profile (VU ramp stages via `scenarios`, plus
`thresholds`) is added per-script when that route's load test is scoped. In load
mode, `fields-combinations.ts` fixes its request to that single worst-case
combination instead of sweeping the smoke test's full fixture — the two profiles
test different things (correctness across shapes vs. a capacity ceiling for the
worst shape), not just different volumes of the same request.
`passages/filter-combinations.ts` fixes to its most structurally complex real
combination the same way, though passages' `filters` clause adds YQL predicates
to one query rather than triggering extra Vespa calls, so there's no
fan-out-maximising combination to chase there the way there is for
`/documents?fields=`. `passages/index.ts` has no combinations to fix at all — it
sweeps the same query fixture in both profiles, since a single Vespa query with
no fan-out has nothing more expensive to target. Passing `-e PROFILE=load` to a
script without one silently falls back to k6's own defaults (1 VU, 1 iteration)
rather than erroring, since `resolveProfile` returns `undefined` for an unknown
profile name (the cloud name is only merged in when a profile is found).

## CI

The [`k6 smoke tests`](../.github/workflows/k6_smoke_tests.yml) workflow runs
smoke mode against production, in parallel, via
[`grafana/run-k6-action`](https://github.com/grafana/run-k6-action). It's
deliberately not merge-gating (production traffic, no staging environment to
target instead) — it runs on `workflow_dispatch` (on demand) and, as a reusable
workflow, right after `deploy-api` succeeds in `merge_to_main.yml`, so a
regression is flagged post-deploy rather than blocking the merge.

The workflow has one job per `routes/<resource>/` group (currently just
`smoke-documents`, scoped to `k6/routes/documents/**/*.ts`) rather than one job
covering all of `routes/`. Each job reports to its own Grafana Cloud k6 project
— see the Grafana section below for why. Adding a new resource (e.g. passages,
when that story lands) means adding a new `smoke-<resource>` job with its own
path glob and project secret, not editing the existing one.

## Grafana

CI runs stream results to Grafana Cloud k6, via `run-k6-action`'s
`cloud-run-locally` mode (its default — `true`) rather than its full
cloud-execution mode (`cloud-run-locally: false`). Both modes get results into
Grafana; the difference is where the load itself is generated. `true` runs k6 on
the GitHub runner (free) and only streams results to Grafana; `false` generates
load from Grafana's own infrastructure, which costs more per test (see the
"on-premises execution adjustment" — cloud-run-locally gets a 25% VUH discount)
for no benefit here, since a GitHub runner easily handles our present load and
there's no IP-allowlist reason to originate traffic from Grafana's network. This
mirrors the `k6 cloud run --local-execution` CLI flag's semantics one-for-one —
the action is a wrapper over the same underlying k6 binary and behaviour.

### Per-resource Grafana projects

Each `routes/<resource>/` group reports to its own Grafana Cloud k6 project,
rather than all of `search-api` sharing one. `search-api` currently serves
`documents`, `passages`, and `labels` from one deployed service, but nothing
here assumes that stays true — if a resource is ever split out into its own
deployed API, its k6 results are already isolated in their own project rather
than needing to be untangled out of a shared one after the fact. The cost is a
little duplication today (one project, one secret, for `documents` alone),
traded for not having to migrate dashboards/history later if the split happens.

Requires these repo secrets. None exist yet as of writing — someone with Grafana
admin access needs to generate them (Testing & synthetics → Performance →
Settings → Access, in the CPR Grafana Cloud org; a **Stack token**, not a
personal token, since this is for CI, not an individual):

- `K6_CLOUD_TOKEN` — the Grafana Cloud k6 Stack API token. Shared across all
  resource groups; a Stack token isn't itself tied to one project.
- `K6_CLOUD_STACK_ID` — the numeric ID of the CPR Grafana Cloud stack (visible
  on the stack's Details page in the Cloud Portal — distinct from the stack slug
  that appears in the Grafana URL). Also shared.
- `K6_CLOUD_<RESOURCE>_PROJECT_ID` — one per resource group (currently just
  `K6_CLOUD_DOCUMENTS_PROJECT_ID`), the Grafana Cloud k6 project that resource's
  runs report under. A Stack-level token must specify a project on every run, so
  this isn't optional. Create the project first in Grafana (Testing & synthetics
  → Performance → Projects → new project, named after the resource, e.g.
  `documents`) — its ID only exists once the project does.

Until these secrets are set, the `k6 smoke tests` workflow will fail at the
`run-k6-action` step with an authentication error — this is expected and does
not indicate a problem with the scripts themselves.
