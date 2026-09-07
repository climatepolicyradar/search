import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, SLEEP_SECONDS, resolveProfile } from "../../config.ts";

// SharedArray shares this data once across all VUs instead of every VU
// holding its own copy in memory.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const searchQueries = new SharedArray("search-queries", function () {
  return [
    "climate adaptation",
    "deforestation",
    "carbon pricing",
    "renewable energy",
    "flood risk",
  ];
});

type TPassageResult = { text_block_id?: unknown; document_id?: unknown };
type TSearchResponse = { results?: TPassageResult[] };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
    // A failed check() alone doesn't fail the run — it only shows up as a
    // pass-rate in the summary. This threshold makes anything below 100% of
    // checks passing exit the run non-zero, which is the bar for a smoke test.
    // https://grafana.com/docs/k6/latest/using-k6/thresholds/
    thresholds: { checks: ["rate==1.00"] },
  },
  load: {
    // Two phases test two different things, per review feedback on the
    // original single 3-step ramp (10/25/50 VUs, 30s climbs, 1m holds):
    // that shape only measures reactivity to a rapid spike, not the
    // sustained-throughput ceiling, since search-api's autoscaling never
    // gets time to act during it. search-api is ECS Fargate with
    // target-tracking on AVERAGE_CPU at 70%, 1-4 tasks
    // (search/infra/__main__.py:606-639); that policy exposes no
    // configurable cooldown, and AWS's target-tracking re-evaluation plus a
    // fresh Fargate task registering healthy behind the load balancer both
    // take a few minutes, so a 1m hold can complete the whole ramp on a
    // single task and never observe a scale-out.
    //
    // Phase 1 (sustained ceiling): a slow 2m climb into each of 10/25/50
    // VUs, holding 6m at each — long enough to sustain CPU above the 70%
    // target and let task count settle — so a capacity cliff shows up tied
    // to a specific, autoscaled-for VU count rather than an artefact of the
    // ramp outrunning ECS.
    //
    // Phase 2 (spike reactivity): ramp back to a near-zero baseline, hold
    // long enough for ECS to have scaled in again, then jump straight to 50
    // VUs in 15s. This isolates "how fast can it react to a sudden spike"
    // against a known low-scale starting point, rather than measuring a
    // spike on top of whatever task count phase 1 left behind.
    //
    // /search/passages is a single Vespa query with a 5s timeout
    // (search/engines/dev_vespa.py:1363) — no fan-out, unlike
    // /documents?fields=, so this profile doesn't need a worst-case-
    // combination fixed request the way fields-combinations.ts does;
    // sweeping the smoke test's query fixture is representative enough on
    // its own.
    scenarios: {
      rampingLoad: {
        executor: "ramping-vus",
        startVUs: 0,
        stages: [
          // Phase 1: sustained ceiling
          { duration: "2m", target: 10 },
          { duration: "6m", target: 10 },
          { duration: "2m", target: 25 },
          { duration: "6m", target: 25 },
          { duration: "2m", target: 50 },
          { duration: "6m", target: 50 },
          // Reset to baseline, giving ECS time to scale back in
          { duration: "1m", target: 2 },
          { duration: "5m", target: 2 },
          // Phase 2: spike reactivity
          { duration: "15s", target: 50 },
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
  sleep(SLEEP_SECONDS);
}
