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
across separate smoke/load files:

```bash
k6 run routes/documents/index.ts               # smoke (default)
k6 run -e PROFILE=smoke routes/documents/index.ts
k6 run -e PROFILE=load routes/documents/index.ts # once a load profile exists
```

Today only the `smoke` profile is defined: low VUs (2-5), short duration
(~1min), checking for zero failed checks — see k6's
[smoke testing guide](https://grafana.com/docs/k6/latest/testing-guides/test-types/smoke-testing/).
A `load` profile (VU ramp stages, thresholds) is added per-script when that
route's load test is scoped — see FUS-356 for `{document_id}/index.ts`.
