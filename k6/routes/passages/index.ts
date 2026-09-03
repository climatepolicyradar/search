import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const searchQueries = new SharedArray("search-queries", function () {
  return JSON.parse(open("./fixtures/search-queries.json"));
});

type TPassageResult = { text_block_id?: unknown; document_id?: unknown };
type TSearchResponse = { results?: TPassageResult[] };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
  load: {
    // ramp to 50 VUs in 3 steps (10/25/50), holding briefly at each rather
    // than jumping straight to peak, so a capacity cliff shows up as a clear
    // step change tied to a specific VU count instead of an ambiguous
    // average over the whole run. /search/passages is a single Vespa query
    // with a 5s timeout (search/engines/dev_vespa.py:1363) — no fan-out,
    // unlike /documents?fields=, so this profile doesn't need a
    // worst-case-combination fixed request the way fields-combinations.ts
    // does; sweeping the smoke test's query fixture is representative enough
    // on its own. Same shape as documents/{document_id}/index.ts (FUS-356),
    // the closest documents analog (also a single, non-fan-out request).
    scenarios: {
      rampingLoad: {
        executor: "ramping-vus",
        startVUs: 0,
        stages: [
          { duration: "30s", target: 10 },
          { duration: "1m", target: 10 },
          { duration: "30s", target: 25 },
          { duration: "1m", target: 25 },
          { duration: "30s", target: 50 },
          { duration: "1m", target: 50 },
          { duration: "30s", target: 0 },
        ],
      },
    },
    // Thresholds: p95 < 2s is the "existing 2s p95 line on the vespa-search
    // dashboard" the monitoring RFC names
    // (https://app.notion.com/p/3c79109609a48195972fd340c03d1508) — but that RFC
    // explicitly defers formalising it as a real SLO ("Deferred, not rejected —
    // no baseline data yet", still Open as of writing), so treat this as a
    // provisional, not agreed, target until that decision lands. Reused as-is
    // from documents' graduated thresholds (FUS-356/FUS-357) — the RFC figure
    // is a route-agnostic dashboard line, not per-route, so there's no
    // separate number to reference yet. http_req_failed aborts the run early
    // on a failure spike rather than burning the full ramp on a route that's
    // already broken.
    thresholds: {
      // PROVISIONAL — see comment above. Not an agreed SLO.
      http_req_duration: ["p(95)<2000"],
      http_req_failed: [{ threshold: "rate<0.01", abortOnFail: true }],
    },
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile("passages: base query", PROFILES);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const query = searchQueries[Math.floor(Math.random() * searchQueries.length)];
  // No order_by param: defaults to `idx asc` (reading order, not relevance)
  // per the OpenAPI schema — this is the base case's actual default
  // behaviour, distinct from /documents defaulting to `relevance desc`.
  const res = http.get(
    `${BASE_URL}/passages?query=${encodeURIComponent(query)}`,
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    "status is 200": (response: Response) => response.status === 200,
    "response has results array": (response: Response) => {
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    "results have text_block_id and document_id": (response: Response) => {
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      return (
        results.length > 0 &&
        results.every(
          (result) =>
            typeof result?.text_block_id === "string" &&
            typeof result?.document_id === "string",
        )
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
