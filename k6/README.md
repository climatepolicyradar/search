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

## Layout

One folder per search-api resource, one file per route (named after what it
hits, not after a test type):

```text
k6/
  documents/
    document-by-id.ts   # GET /search/documents/{document_id}
    search-documents.ts # GET /search/documents
    fixtures/
      document-ids.json  # real, pre-verified document_ids
      search-queries.json # realistic free-text search terms
```

## Running

```bash
k6 run k6/documents/document-by-id.ts
k6 run k6/documents/search-documents.ts
```

Defaults to hitting production (`https://api.climatepolicyradar.org/search`).
Override with `BASE_URL`:

```bash
BASE_URL=https://staging.example.com/search k6 run k6/documents/document-by-id.ts
```

## Smoke vs. load: one file, one `PROFILE`

Each script exports a `PROFILES` map and picks one via `-e PROFILE=<name>`
(defaulting to `smoke` if unset), rather than duplicating the request logic
across separate smoke/load files:

```bash
k6 run k6/documents/document-by-id.ts               # smoke (default)
k6 run -e PROFILE=smoke k6/documents/document-by-id.ts
k6 run -e PROFILE=load k6/documents/document-by-id.ts # once a load profile exists
```

Today only the `smoke` profile is defined: low VUs (2-5), short duration
(~1min), checking for zero failed checks — see k6's
[smoke testing guide](https://grafana.com/docs/k6/latest/testing-guides/test-types/smoke-testing/).
A `load` profile (VU ramp stages, thresholds) is added per-script when that
route's load test is scoped — see FUS-356 for `document-by-id.ts`.
