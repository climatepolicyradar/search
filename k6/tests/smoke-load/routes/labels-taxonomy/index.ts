import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import tempo from "https://jslib.k6.io/http-instrumentation-tempo/1.0.1/index.js";

// __ENV reads a variable passed on the command line, e.g. `-e BASE_URL=...`.
// Defaults to production so `k6 run` works out of the box with no setup.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/environment-variables/
const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

// Inter-request pause within the single full sweep this script runs (see
// default() below). Lower than the suite's usual 1s default: this isn't a
// repeating per-VU loop pacing against simulated user think time, it's one
// deterministic pass over every taxonomy label, and at ~58 labels (as of
// writing — see api/labels_taxonomy.py) a 1s pause would make the run take
// a minute-plus on pacing alone. 0.2s still avoids hammering the endpoint
// back-to-back. Override with `-e SLEEP_SECONDS=...`.
const SLEEP_SECONDS = Number(__ENV.SLEEP_SECONDS ?? 0.2);

// A VU ("virtual user") is one simulated concurrent user — it runs a script's
// default-exported function in a loop for `duration`. PROFILES below is
// picked via `-e PROFILE=<name>`. With no env var set, defaults to `load` if
// PROFILES has one, else whichever profile is listed first (`smoke`, by
// convention — see PROFILES below). CI's smoke workflow passes
// `-e PROFILE=smoke` explicitly.
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

type TLabel = { id?: unknown };
type TTaxonomyResponse = { results?: TLabel[] };
type TDocumentResult = { id?: unknown; title?: unknown };
type TSearchResponse = { results?: TDocumentResult[]; total_size?: number };

// No "load" profile: this isn't a capacity test, it's a correctness sweep —
// one deterministic pass over the whole taxonomy, not a repeated/ramped
// request pattern, so VU ramp stages and latency thresholds don't apply the
// way they do for the rest of this suite's scripts.
const PROFILES = {
  smoke: {
    // A single VU running a single iteration: default() below loops over
    // every taxonomy label itself, so there's nothing for extra VUs or
    // iterations to parallelise — doing so would just repeat the same full
    // sweep redundantly.
    vus: 1,
    iterations: 1,
    // A failed check() alone doesn't fail the run — it only shows up as a
    // pass-rate in the summary. This threshold makes anything below 100% of
    // checks passing exit the run non-zero, which is the bar for a smoke test.
    // https://grafana.com/docs/k6/latest/using-k6/thresholds/
    thresholds: { checks: ["rate==1.00"] },
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// iteration config for the run, not a convention we chose.
export const options = resolveProfile(
  "labels-taxonomy: filter coverage",
  PROFILES,
);

// Distributed tracing: attaches a W3C `traceparent` header — the format
// OTel's default propagator reads — to every HTTP request from this point
// forward and tags each request's trace_id in the output metadata, so
// Grafana Cloud k6 can correlate this run's requests with server-side spans
// in Grafana Cloud Traces (Tempo).
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
tempo.instrumentHTTP({
  propagator: "w3c",
});

// setup() runs once before any VU iteration and is the one place in a k6
// script allowed to do request-time work ahead of the timed run — used here
// to fetch the taxonomy live rather than inlining a hardcoded label list
// (unlike this suite's other fixtures — see k6/README.md's fixture-inlining
// note). A hardcoded copy would silently drift from api/labels_taxonomy.py
// and stop catching the exact thing this test exists to catch: a label in
// the taxonomy with no matching documents.
export function setup(): { ids: string[] } {
  const res = http.get(`${BASE_URL}/labels-taxonomy`, {
    tags: { name: "labels-taxonomy" },
  });
  const body = res.json() as TTaxonomyResponse;
  const ids = (body?.results ?? [])
    .map((label) => label?.id)
    .filter((id): id is string => typeof id === "string");
  if (ids.length === 0) {
    throw new Error(
      `GET ${BASE_URL}/labels-taxonomy returned no usable label ids (status ${res.status})`,
    );
  }
  return { ids };
}

// k6 calls this function once per VU iteration for the whole run — here,
// once total (see PROFILES.smoke above), and it sweeps every id from
// setup() itself rather than sampling one per call like this suite's other
// filter-combinations scripts. The ask this test exists to answer is "does
// every taxonomy label actually filter to at least one document", which
// means every label has to be checked, not a random subset of them.
export default function (data: { ids: string[] }) {
  for (const id of data.ids) {
    const filters = {
      op: "and",
      filters: [{ field: "labels.value.id", op: "contains", value: id }],
    };
    const res = http.get(
      `${BASE_URL}/documents?filters=${encodeURIComponent(JSON.stringify(filters))}`,
      {
        // Group by route path + the relevant query param *names* (never
        // values) — see k6/README.md's Metric tag naming section. Every
        // request in this sweep shares the same param name (`filters`), only
        // its value changes per label, so they all share one tag here.
        tags: { name: "documents?filters", url: "documents?filters" },
      },
    );

    // k6 check names may not contain "::" — taxonomy ids use it as a
    // type/value separator (e.g. "category::Report"), so strip it for
    // display only.
    const checkLabel = id.replace(/::/g, ":");

    // check() records pass/fail per assertion without stopping the loop on
    // failure (unlike a thrown error) — a single label with zero documents
    // shows up as one failed check among the rest, rather than aborting the
    // sweep before every other label has been checked too.
    // https://grafana.com/docs/k6/latest/using-k6/checks/
    check(res, {
      [`${checkLabel}: status is 200`]: (response: Response) =>
        response.status === 200,
      [`${checkLabel}: filters to at least 1 document`]: (
        response: Response,
      ) => {
        if (response.status !== 200) return false;
        const body = response.json() as TSearchResponse;
        // total_size is the authoritative count: a non-default page_size
        // could otherwise truncate `results` even when matches exist.
        return (body?.total_size ?? 0) > 0;
      },
    });

    sleep(SLEEP_SECONDS);
  }
}
