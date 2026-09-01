import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const documentIds = new SharedArray("document-ids", function () {
  return JSON.parse(open("./fixtures/document-ids.json"));
});

type TDocumentResponse = { data?: { id?: string; title?: unknown } };

// `load` ramps to 50 VUs (the cheapest document route — single-doc fetch by
// path param, no Vespa fan-out — so this is a starting point, not a
// pre-validated ceiling) in 3 steps (10/25/50), holding briefly at each
// rather than jumping straight to peak, so a capacity cliff shows up as a
// clear step change tied to a specific VU count instead of an ambiguous
// average over the whole run.
//
// Thresholds: p95 < 2s is the "existing 2s p95 line on the vespa-search
// dashboard" the monitoring RFC names
// (https://app.notion.com/p/3c79109609a48195972fd340c03d1508) — but that RFC
// explicitly defers formalising it as a real SLO ("Deferred, not rejected —
// no baseline data yet"), so treat this as a provisional, not agreed, target
// until that decision lands. http_req_failed aborts the run early on a
// failure spike rather than burning the full ramp on a route that's already
// broken.
const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
  load: {
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
    thresholds: {
      // PROVISIONAL — see comment above. Not an agreed SLO.
      http_req_duration: ["p(95)<2000"],
      http_req_failed: [{ threshold: "rate<0.01", abortOnFail: true }],
    },
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(PROFILES);

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
  sleep(1);
}
