import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import tempo from "k6/experimental/tracing";

// __ENV reads a variable passed on the command line, e.g. `-e BASE_URL=...`.
// Defaults to production so `k6 run` works out of the box with no setup.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/environment-variables/
const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

// Per-iteration pause each VU takes between requests (`sleep(SLEEP_SECONDS)`
// at the end of this script's default function). Configurable so the request
// rate can be dialled without touching VU count — e.g. `-e SLEEP_SECONDS=0.1`
// to push a heavier load, or a larger value to space requests out. Defaults
// to 1s of simulated think time, the standard smoke/load-test pacing.
const SLEEP_SECONDS = Number(__ENV.SLEEP_SECONDS ?? 1);

// A VU ("virtual user") is one simulated concurrent user — it runs a script's
// default-exported function in a loop for `duration`. PROFILES below (VUs/
// duration differ per route, and a `load` profile is added once that route's
// load test is scoped) is picked via `-e PROFILE=<name>`. With no env var
// set, defaults to `load` if PROFILES has one, else whichever profile is
// listed first (`smoke`, by convention — see PROFILES below). Defaulting to
// `load` when available matters for scripts uploaded to Grafana Cloud k6 as a
// scheduled LoadTest resource (see infra/k6_load_tests.py) — Cloud has no way
// to pass `-e PROFILE=...` at trigger time, so whatever this resolves to with
// no env var set is what a scheduled cloud run always executes. CI's smoke
// workflow and any local smoke check must pass `-e PROFILE=smoke` explicitly
// once a script has a load profile; it is no longer the no-flags default.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/
//
// `cloudName` sets `options.cloud.name`, the identifier Grafana Cloud k6 uses
// to group this script's runs. Without it, Cloud falls back to the script's
// own filename — multiple routes named `index.ts` (the base-query convention,
// see k6/README.md's Layout section) then collide under one indistinguishable
// "index.ts" name in the project's runs list.
function resolveProfile(
  cloudName: string,
  profiles: Record<string, object>,
): object {
  const defaultProfileName =
    "load" in profiles ? "load" : Object.keys(profiles)[0];
  const profile = profiles[__ENV.PROFILE || defaultProfileName] as
    | Record<string, unknown>
    | undefined;
  if (!profile) return profile as unknown as object;
  return { ...profile, cloud: { name: cloudName } };
}

// SharedArray shares this data once across all VUs instead of every VU
// holding its own copy in memory.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
//
// Confirmed via the production OpenAPI schema
// (https://api.climatepolicyradar.org/search/openapi.json): two sortable
// fields (relevance, idx), each asc/desc — 4 combinations, all covered here
// per FUS-350's scope (the documents story's separate "default" flag doesn't
// apply the same way: `idx asc` IS the default here, so it's both the first
// fixture entry and flagged `isDefault` rather than a 5th separate case).
// `idx asc` is what the base query (FUS-348) already exercises unset — this
// file additionally requests it explicitly to confirm the param round-trips.
// `relevance` has no externally-verifiable deterministic order, so only the
// `idx` cases assert actual sort order; all cases assert the request
// succeeds with well-formed results. Verified live:
// `relevance asc` returns results identical to `relevance desc`, matching
// `_ranking_overrides_for_passage_order_by`'s behaviour
// (search/engines/dev_vespa.py) of falling back to `relevance` (desc)
// ranking with a warning rather than erroring — asc is accepted but not
// actually a distinct ordering, so this is asserted explicitly rather than
// glossed over as "just another combination".
type TOrderByCombination = {
  orderBy: string;
  isDefault: boolean;
  sortField: "idx" | null;
  sortDirection: "asc" | "desc" | null;
};

const orderByCombinations = new SharedArray(
  "order-by-combinations",
  function (): TOrderByCombination[] {
    return [
      {
        orderBy: "idx asc",
        isDefault: true,
        sortField: "idx",
        sortDirection: "asc",
      },
      {
        orderBy: "idx desc",
        isDefault: false,
        sortField: "idx",
        sortDirection: "desc",
      },
      {
        orderBy: "relevance desc",
        isDefault: false,
        sortField: null,
        sortDirection: null,
      },
      {
        orderBy: "relevance asc",
        isDefault: false,
        sortField: null,
        sortDirection: null,
      },
    ];
  },
);

// `idx` only orders passages within a single document (confirmed live:
// without a document_id filter, results are grouped by relevance first, and
// `idx` is not a meaningful global sort key) — so this test fixes the query
// to a single, stable document with a large passage count (629 passages at
// time of writing) rather than the documents story's broad free-text query.
const FIXED_DOCUMENT_ID = "CCLW.document.i00007398.n0000";
const FIXED_FILTERS = encodeURIComponent(
  JSON.stringify({
    op: "and",
    filters: [
      { field: "document_id", op: "contains", value: FIXED_DOCUMENT_ID },
    ],
  }),
);

type TPassageResult = {
  text_block_id?: unknown;
  document_id?: unknown;
  idx?: unknown;
};
type TSearchResponse = { results?: TPassageResult[] };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(
  "passages: order_by combinations",
  PROFILES,
);

// Distributed tracing: attaches a W3C `traceparent` header to every HTTP
// request from this point forward and tags each request's trace_id in the
// output metadata, so Grafana Cloud k6 can correlate this run's requests
// with server-side spans in Grafana Cloud Traces (Tempo). This is the
// k6-x-tempo feature the Cloud Insights recommendations flagged for this
// test. Requires search-api's OTel setup to extract the incoming
// traceparent header for the trace to actually correlate — see
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
tempo.instrumentHTTP({
  propagator: "w3c",
});

function isSorted(
  results: TPassageResult[],
  direction: "asc" | "desc",
): boolean {
  const values = results.map((result) => Number(result.idx ?? 0));
  for (let i = 1; i < values.length; i++) {
    if (
      direction === "asc"
        ? values[i - 1] > values[i]
        : values[i - 1] < values[i]
    ) {
      return false;
    }
  }
  return true;
}

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    orderByCombinations[Math.floor(Math.random() * orderByCombinations.length)];
  const res = http.get(
    `${BASE_URL}/passages?query=climate&filters=${FIXED_FILTERS}&order_by=${encodeURIComponent(combination.orderBy)}`,
    {
      // Group by the fixed order_by value instead of letting k6 default
      // `name`/`url` to the full dynamic query string — per-request order_by
      // text was producing a high-cardinality set of unique values across
      // http_reqs, http_req_waiting, and http_req_tls_handshaking (flagged by
      // Cloud Insights' Metric Tags audit). This collapses all requests
      // sharing an order_by value into one series per combination.
      // https://grafana.com/docs/k6/latest/using-k6/http-requests/#url-grouping
      tags: { name: `passages:order_by:${combination.orderBy}` },
    },
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  //
  // Assertions are deliberately layered — response shape, then a non-empty
  // result set, then per-result field types are separate named checks rather
  // than one combined boolean. If the response contract regresses (results
  // key renamed, text_block_id changes type, an error body comes back with
  // 200) the failing check name points at which assumption broke, instead of
  // a single opaque "expectation not met".
  check(res, {
    [`${combination.orderBy}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${combination.orderBy}: response has results array`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    [`${combination.orderBy}: response has results`]: (response: Response) => {
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results) && body.results.length > 0;
    },
    [`${combination.orderBy}: results have string text_block_id and document_id`]:
      (response: Response) => {
        const body = response.json() as TSearchResponse;
        const results = body?.results ?? [];
        return results.every(
          (result) =>
            typeof result?.text_block_id === "string" &&
            typeof result?.document_id === "string",
        );
      },
    [`${combination.orderBy}: results are sorted`]: (response: Response) => {
      if (
        combination.sortField === null ||
        combination.sortDirection === null
      ) {
        return true;
      }
      const body = response.json() as TSearchResponse;
      return isSorted(body?.results ?? [], combination.sortDirection);
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
