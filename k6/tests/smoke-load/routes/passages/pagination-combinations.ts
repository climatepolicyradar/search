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
// `page_token` is a 1-based page number; search-api computes Vespa's offset
// as `(page_token - 1) * page_size` (search/engines/dev_vespa.py, same
// pagination logic as /documents). Covers the first page (default), a deep
// page (offset 490 — tests the cost of Vespa skipping over ranked results
// internally), and a large `page_size`. The fixed `query=climate` result set
// (over a million passages at time of writing) is large enough that all
// three cases return full pages.
type TPaginationCombination = {
  name: string;
  pageToken: number;
  pageSize: number;
  verifyOffsetAdvances: boolean;
};

const paginationCombinations = new SharedArray(
  "pagination-combinations",
  function (): TPaginationCombination[] {
    return [
      {
        name: "first page (default)",
        pageToken: 1,
        pageSize: 10,
        verifyOffsetAdvances: false,
      },
      {
        name: "deep page (tests offset cost)",
        pageToken: 50,
        pageSize: 10,
        verifyOffsetAdvances: true,
      },
      {
        name: "large page_size",
        pageToken: 1,
        pageSize: 100,
        verifyOffsetAdvances: false,
      },
    ];
  },
);

type TPassageResult = { text_block_id?: unknown; document_id?: unknown };
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
  "passages: pagination combinations",
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

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    paginationCombinations[
      Math.floor(Math.random() * paginationCombinations.length)
    ];
  const res = http.get(
    `${BASE_URL}/passages?query=climate&page_token=${combination.pageToken}&page_size=${combination.pageSize}`,
    {
      // Group by the fixed combination name instead of letting k6 default
      // `name`/`url` to the full dynamic query string — per-request
      // page_token/page_size values were producing a high-cardinality set of
      // unique values across http_reqs, http_req_waiting, and
      // http_req_tls_handshaking (flagged by Cloud Insights' Metric Tags
      // audit). This collapses all requests sharing a pagination combination
      // into one series per combination.
      // https://grafana.com/docs/k6/latest/using-k6/http-requests/#url-grouping
      tags: { name: `passages:${combination.name}` },
    },
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  //
  // Assertions are deliberately layered — response shape, then the page-size
  // count, then per-result field types are separate named checks rather than
  // one combined boolean. If the response contract regresses (results key
  // renamed, text_block_id changes type, an error body comes back with 200)
  // the failing check name points at which assumption broke, instead of a
  // single opaque "expectation not met".
  check(res, {
    [`${combination.name}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${combination.name}: response has results array`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    [`${combination.name}: returns exactly page_size results`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      return (body?.results ?? []).length === combination.pageSize;
    },
    [`${combination.name}: results have string text_block_id and document_id`]:
      (response: Response) => {
        const body = response.json() as TSearchResponse;
        const results = body?.results ?? [];
        return results.every(
          (result) =>
            typeof result?.text_block_id === "string" &&
            typeof result?.document_id === "string",
        );
      },
  });

  if (combination.verifyOffsetAdvances) {
    // Proves the offset is actually taking effect, not silently ignored:
    // a deep page must return different passages than page 1.
    const firstPageRes = http.get(
      `${BASE_URL}/passages?query=climate&page_token=1&page_size=${combination.pageSize}`,
      { tags: { name: "passages:first page (default)" } },
    );
    check(firstPageRes, {
      [`${combination.name}: differs from page 1`]: () => {
        const deepPageBody = res.json() as TSearchResponse;
        const firstPageBody = firstPageRes.json() as TSearchResponse;
        const deepPageIds = (deepPageBody?.results ?? []).map(
          (r) => r.text_block_id,
        );
        const firstPageIds = (firstPageBody?.results ?? []).map(
          (r) => r.text_block_id,
        );
        return JSON.stringify(deepPageIds) !== JSON.stringify(firstPageIds);
      },
    });
  }

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
