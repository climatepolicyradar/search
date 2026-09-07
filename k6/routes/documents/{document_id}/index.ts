import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, SLEEP_SECONDS, resolveProfile } from "../../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const documentIds = new SharedArray("document-ids", function () {
  return JSON.parse(open("./fixtures/document-ids.json"));
});

type TDocumentResponse = { data?: { id?: string; title?: unknown } };

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
    // VUs (this route is the cheapest document route — single-doc fetch by
    // path param, no Vespa fan-out — so this is a starting point, not a
    // pre-validated ceiling), holding 6m at each — long enough to sustain
    // CPU above the 70% target and let task count settle — so a capacity
    // cliff shows up tied to a specific, autoscaled-for VU count rather than
    // an artefact of the ramp outrunning ECS.
    //
    // Phase 2 (spike reactivity): ramp back to a near-zero baseline, hold
    // long enough for ECS to have scaled in again, then jump straight to 50
    // VUs in 15s. This isolates "how fast can it react to a sudden spike"
    // against a known low-scale starting point, rather than measuring a
    // spike on top of whatever task count phase 1 left behind.
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
    // no baseline data yet"), so treat this as a provisional, not agreed, target
    // until that decision lands. http_req_failed aborts the run early on a
    // failure spike rather than burning the full ramp on a route that's already
    // broken.
    thresholds: {
      // PROVISIONAL — see comment above. Not an agreed SLO.
      http_req_duration: ["p(95)<2000"],
      http_req_failed: [{ threshold: "rate<0.01", abortOnFail: true }],
    },
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(
  "documents/{document_id}: base query",
  PROFILES,
);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const documentId =
    documentIds[Math.floor(Math.random() * documentIds.length)];
  const res = http.get(`${BASE_URL}/documents/${documentId}`);

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    "status is 200": (response: Response) => response.status === 200,
    "response has matching data.id": (response: Response) => {
      const body = response.json() as TDocumentResponse;
      return body?.data?.id === documentId;
    },
    "response has data.title": (response: Response) => {
      const body = response.json() as TDocumentResponse;
      return (
        typeof body?.data?.title === "string" && body.data.title.length > 0
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
