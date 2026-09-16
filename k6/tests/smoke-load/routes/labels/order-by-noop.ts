import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import tempo from "https://jslib.k6.io/http-instrumentation-tempo/1.0.1/index.js";

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
// default-exported function in a loop for `duration`. PROFILES below is
// picked via `-e PROFILE=<name>`, defaulting to whichever is listed first
// (`smoke`, by convention) when there's no `load` entry — see
// k6/README.md's Layout section.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/
//
// `cloudName` sets `options.cloud.name`, the identifier Grafana Cloud k6 uses
// to group this script's runs. Without it, Cloud falls back to the script's
// own filename.
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

// FUS-354 asked to confirm sortable order_by fields for /search/labels
// against the engine code, the way documents/order-by-combinations.ts and
// passages/order-by-combinations.ts do for their routes. There are none:
// `DevVespaLabelSearchEngine.search()` (search/engines/dev_vespa.py) takes
// `order_by: list[OrderBy]` annotated `# noqa: ARG002` (an explicit unused-
// argument lint suppression) and never references it in the method body —
// the Vespa request body hardcodes `"ranking.profile": "nativerank"` with no
// sort override at all. The parameter only exists because
// `DevVespaLabelSearchEngine` implements the abstract `SearchEngine.search()`
// signature (search/engines/__init__.py), which requires it for
// documents/passages; labels never wired up an implementation.
// `api/routers.py`'s `read_labels` still accepts and parses any
// `order_by=<field> <direction>` value via the shared generic dependency (no
// per-route field validation, unlike documents/passages) — so a nonsense
// order_by string parses successfully and is silently dropped, not
// rejected.
//
// Confirmed with search-api's owning team (#team-fusion, 2026-09-16, James
// Gorrie): this is deliberate/known, not a bug to fix as part of this
// story — required by the base class, genuinely unimplemented for labels.
//
// So there's no order-by-combinations.ts for this route (unlike documents/
// passages) — instead, this test is a regression guard on the no-op itself:
// two different order_by values must return results in the same order. If
// someone later wires up real sorting for labels, this test starts failing,
// which is the intended signal to update it (and this comment) rather than
// silently going stale.
const PROFILES = {
  smoke: {
    vus: 2,
    duration: "30s",
    // A failed check() alone doesn't fail the run — it only shows up as a
    // pass-rate in the summary. This threshold makes anything below 100% of
    // checks passing exit the run non-zero, which is the bar for a smoke test.
    // https://grafana.com/docs/k6/latest/using-k6/thresholds/
    thresholds: { checks: ["rate==1.00"] },
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile("labels: order_by is a no-op", PROFILES);

// Distributed tracing: attaches a W3C `traceparent` header — the format
// OTel's default propagator reads — to every HTTP request from this point
// forward and tags each request's trace_id in the output metadata, so
// Grafana Cloud k6 can correlate this run's requests with server-side spans
// in Grafana Cloud Traces (Tempo).
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
tempo.instrumentHTTP({
  propagator: "w3c",
});

type TLabelResult = { id?: unknown };
type TSearchResponse = { results?: TLabelResult[] };

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  // No `query` param: a broad, unfiltered listing gives the largest, most
  // stable result set to compare order across, minimising the chance two
  // requests differ in *content* rather than *order* due to Vespa's index
  // state changing between calls (e.g. an in-flight feed).
  const defaultOrderRes = http.get(`${BASE_URL}/labels?page_size=50`, {
    tags: { name: "labels?order_by" },
  });
  const reversedOrderRes = http.get(
    `${BASE_URL}/labels?page_size=50&order_by=${encodeURIComponent("relevance asc")}`,
    { tags: { name: "labels?order_by" } },
  );

  check(defaultOrderRes, {
    "default order_by: status is 200": (response: Response) =>
      response.status === 200,
  });
  check(reversedOrderRes, {
    "order_by=relevance asc: status is 200": (response: Response) =>
      response.status === 200,
    "order_by has no effect on result order (documents the confirmed no-op)": (
      response: Response,
    ) => {
      if (response.status !== 200 || defaultOrderRes.status !== 200) {
        return false;
      }
      const defaultBody = defaultOrderRes.json() as TSearchResponse;
      const reversedBody = response.json() as TSearchResponse;
      const defaultIds = (defaultBody?.results ?? []).map((r) => r.id);
      const reversedIds = (reversedBody?.results ?? []).map((r) => r.id);
      return (
        defaultIds.length > 0 &&
        JSON.stringify(defaultIds) === JSON.stringify(reversedIds)
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
