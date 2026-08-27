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

One folder per search-api resource:

```text
k6/
  documents/
    smoke.ts               # GET /search/documents/{document_id}
    fixtures/
      document-ids.json    # real, pre-verified document_ids
```

## Running

```bash
k6 run k6/documents/smoke.ts
```

Defaults to hitting production (`https://api.climatepolicyradar.org/search`).
Override with `BASE_URL`:

```bash
BASE_URL=https://staging.example.com/search k6 run k6/documents/smoke.ts
```

## Smoke vs. load tests

These scripts start as smoke tests: low VUs (2-5), short duration (~1min),
checking for zero failed checks — see k6's
[smoke testing guide](https://grafana.com/docs/k6/latest/testing-guides/test-types/smoke-testing/).
