import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import tempo from "https://jslib.k6.io/http-instrumentation-tempo/1.0.1/index.js";

// __ENV reads a variable passed on the command line, e.g. `-e BASE_URL=...`.
// Defaults to production so `k6 run` works out of the box with no setup.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/environment-variables/
const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

// Per-iteration pause each VU takes between requests (`sleep(SLEEP_SECONDS)`
// at the end of this script's default function).
const SLEEP_SECONDS = Number(__ENV.SLEEP_SECONDS ?? 1);

// A VU ("virtual user") is one simulated concurrent user — it runs a script's
// default-exported function in a loop for `duration`. PROFILES below is
// picked via `-e PROFILE=<name>`. This route has smoke only, deliberately —
// see the note below `PROFILES`.
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

// FUS-340's ticket text originally excluded this route ("Won't have"), on
// the assumption it wasn't real product surface. It is: navigator-frontend
// calls it directly (src/hooks/useLabelSearch.ts's loadLabelTaxonomy) and
// merges its results with /search/labels to build the sidebar filter tree
// (src/pages/_search/index.tsx) — a temporary workaround for a data-lake
// taxonomy issue (linked from that file: APP-2266), not dead code.
//
// Deliberately smoke-only, no `load` profile: read_labels_taxonomy()
// (api/routers.py) returns a hardcoded in-memory Python list
// (api/labels_taxonomy.py, ~56 entries at time of writing) with no Vespa
// call and no I/O at all — there is no meaningful capacity ceiling to find
// here beyond FastAPI/ASGI's own baseline throughput, which the documents/
// passages/labels breakpoint runs already characterise for this service.
// Smoke coverage (200 + stable shape/count) is what actually matters: a
// regression here would be a code change breaking serialisation or the
// hardcoded list itself, not a load-related failure.
const PROFILES = {
  smoke: {
    vus: 3,
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
export const options = resolveProfile("labels-taxonomy: base query", PROFILES);

// Distributed tracing: attaches a W3C `traceparent` header — the format
// OTel's default propagator reads — to every HTTP request from this point
// forward and tags each request's trace_id in the output metadata, so
// Grafana Cloud k6 can correlate this run's requests with server-side spans
// in Grafana Cloud Traces (Tempo).
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
tempo.instrumentHTTP({
  propagator: "w3c",
});

type TLabelResult = { id?: unknown; type?: unknown; value?: unknown };
type TSearchResponse = { results?: TLabelResult[]; total_size?: number };

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  // No query params: this route takes none (api/routers.py's
  // read_labels_taxonomy has no Query dependencies at all).
  const res = http.get(`${BASE_URL}/labels-taxonomy`, {
    tags: { name: "labels-taxonomy" },
  });

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    "status is 200": (response: Response) => response.status === 200,
    "response has results array": (response: Response) => {
      if (response.status !== 200) return false;
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    "results have id, type and value": (response: Response) => {
      if (response.status !== 200) return false;
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      return (
        results.length > 0 &&
        results.every(
          (result) =>
            typeof result?.id === "string" &&
            typeof result?.type === "string" &&
            typeof result?.value === "string",
        )
      );
    },
    "total_size matches results length (hardcoded list, always one full page)":
      (response: Response) => {
        if (response.status !== 200) return false;
        const body = response.json() as TSearchResponse;
        return body?.total_size === (body?.results ?? []).length;
      },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
