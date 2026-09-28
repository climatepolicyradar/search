import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
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

// Resolved the same way resolveProfile picks a default above — a script whose
// default() branches on load vs. smoke (e.g. picking one worst-case fixture
// vs. sweeping all of them) must agree with what `options` resolved to, or
// the two would silently disagree once no env var is passed.
const isLoadProfile = (__ENV.PROFILE || "load") === "load";

// SharedArray shares this data once across all VUs instead of every VU
// holding its own copy in memory.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
//
// `filters` is free-form JSON not enumerated in the OpenAPI schema, so these
// combinations are sourced from real usage, not guessed: the shape matches
// search-api's Filter/FieldFilter/AttributesCondition models
// (search/engines/vespa_query/filters.py, see SimpleExampleFilter/
// ComplexExampleFilter there) and is exactly what navigator-frontend sends
// as the `filters` param
// (src/api/search.ts, src/utils/search/filterPathsToQueryGroup.ts). Covers a
// single filter, multiple filters `and`-ed (incl. an AttributesCondition
// date range), a top-level `or` and a nested `or`-in-`and` (both matching
// navigator-frontend's multi-select-within-a-facet shape), and a zero-result
// combination — worth testing explicitly since empty-result queries can
// behave very differently under load than populated ones.
type TFilterCombination = {
  name: string;
  expectZeroResults: boolean;
  filters: unknown;
};

const filterCombinations = new SharedArray(
  "filter-combinations",
  function (): TFilterCombination[] {
    return [
      {
        name: "single filter: category label",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              field: "labels.value.id",
              op: "contains",
              value: "category::Report",
            },
          ],
        },
      },
      {
        name: "combined filters: category + status + published_date range (and)",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              field: "labels.value.id",
              op: "contains",
              value: "category::Report",
            },
            {
              field: "labels.value.id",
              op: "contains",
              value: "status::Principal",
            },
            {
              field: "attributes.published_date",
              key: "published_date",
              op: "gte",
              value: "2015-01-01T00:00:00.000Z",
            },
          ],
        },
      },
      {
        name: "combined filters: category Law or Policy (or)",
        expectZeroResults: false,
        filters: {
          op: "or",
          filters: [
            {
              field: "labels.value.id",
              op: "contains",
              value: "category::Law",
            },
            {
              field: "labels.value.id",
              op: "contains",
              value: "category::Policy",
            },
          ],
        },
      },
      {
        name: "combined filters: (category Law or Policy) and status Principal (nested or-in-and)",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              op: "or",
              filters: [
                {
                  field: "labels.value.id",
                  op: "contains",
                  value: "category::Law",
                },
                {
                  field: "labels.value.id",
                  op: "contains",
                  value: "category::Policy",
                },
              ],
            },
            {
              field: "labels.value.id",
              op: "contains",
              value: "status::Principal",
            },
          ],
        },
      },
      {
        name: "zero-result combination: status filter contradicted by a nonexistent status label",
        expectZeroResults: true,
        filters: {
          op: "and",
          filters: [
            {
              field: "labels.value.id",
              op: "contains",
              value: "status::Principal",
            },
            {
              field: "labels.value.id",
              op: "contains",
              value: "status::NonExistentStatusValue",
            },
          ],
        },
      },
    ];
  },
);

type TDocumentResult = { id?: unknown; title?: unknown };
type TSearchResponse = { results?: TDocumentResult[]; total_size?: number };

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
    // gets time to act during it.
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
    // A `filters` clause adds YQL predicates to /documents' single search
    // query rather than triggering extra Vespa calls the way `fields=`
    // does (see fields-combinations.ts), so there is no fan-out-maximising
    // combination to chase here. Load mode instead fixes the request to
    // the fixture's most structurally complex real shape (the nested
    // or-in-and) as the closest available proxy for "most expensive single
    // query", rather than sweeping all combinations, so a threshold breach
    // is attributable to one specific request shape.
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
    // Thresholds: 2000ms is a loose tripwire above measured healthy
    // capacity, not a fitted SLO. Derived using the method in
    // k6/docs/load-threshold-methodology.md; see
    // k6/docs/results/2026-09-09-breakpoint-test-baseline.md for the
    // measurements this value is based on — three same-day production
    // runs put the healthy region's p95 at 860ms-1.85s and the collapse
    // point (a hard cliff, not gradual) at ~6rps offered load, so 2000ms
    // has real headroom on both sides. Re-derive (new dated results file,
    // method doc unchanged) rather than editing the number here from
    // memory — the underlying capacity is expected to move as
    // infrastructure changes, per that results file's caveats.
    // http_req_failed aborts the run early on a failure spike rather than
    // burning the full ramp on a route that's already broken.
    thresholds: {
      // Loose tripwire, not a tight SLO — see comment above.
      http_req_duration: ["p(95)<2000"],
      http_req_failed: [{ threshold: "rate<0.01", abortOnFail: true }],
    },
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(
  "documents: filter combinations",
  PROFILES,
);

// Distributed tracing: attaches a W3C `traceparent` header — the format
// OTel's default propagator reads — to every HTTP request from this point
// forward and tags each request's trace_id in the output metadata, so
// Grafana Cloud k6 can correlate this run's requests with server-side spans
// in Grafana Cloud Traces (Tempo). This is the k6-x-tempo feature the Cloud
// Insights recommendations flagged for this test. Requires search-api's
// OTel setup to extract the incoming traceparent header for the trace to
// actually correlate — see
// https://grafana.com/docs/k6/latest/javascript-api/jslib/http-instrumentation-tempo
tempo.instrumentHTTP({
  propagator: "w3c",
});

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  // Smoke mode sweeps all combinations to check correctness; load mode
  // repeats the single most structurally complex real shape (the nested
  // or-in-and) to find a capacity ceiling for it — the two profiles are
  // testing different things, not just different volumes of the same thing.
  const combination = isLoadProfile
    ? filterCombinations.find((c) => c.name.includes("nested or-in-and"))!
    : filterCombinations[Math.floor(Math.random() * filterCombinations.length)];
  const filtersParam = encodeURIComponent(JSON.stringify(combination.filters));
  // Load mode always requests the same fixed filter combination, so without
  // a cache-buster it's a single, entirely static URL — CloudFront serves
  // almost every request after the first as a hit, measuring the edge, not
  // origin (see k6/tests/breakpoint/README.md finding 0). Smoke mode sweeps
  // many combinations testing correctness, not capacity, so it's left
  // cacheable.
  const cacheBuster = isLoadProfile
    ? `&_cb=${__VU}-${__ITER}-${Date.now()}`
    : "";
  const res = http.get(
    `${BASE_URL}/documents?filters=${filtersParam}${cacheBuster}`,
    {
      // Group by route path + the relevant query param *names* (never
      // values) instead of letting k6 default `name`/`url` to the full
      // dynamic filters query string plus load-mode cache buster —
      // per-request filters JSON and cache-buster values were producing a
      // high-cardinality set of unique values across http_reqs,
      // http_req_waiting, and http_req_tls_handshaking (flagged by Cloud
      // Insights' Metric Tags audit). Naming convention across this suite:
      // `{path}?{param_names}`, param names only (the cache-buster isn't a
      // real request param, so it's excluded) — see k6/README.md's Layout
      // section.
      // https://grafana.com/docs/k6/latest/using-k6/http-requests/#url-grouping
      //
      // `url` is a separate k6-builtin tag that `name` does NOT override —
      // it still defaults to the literal request URL (cache-buster and
      // all) unless set explicitly here too, which was the actual source
      // of the reported cardinality on other cache-busted routes in this
      // suite. No extra breakdown tag is needed here: load mode always
      // fixes `combination` to the single nested or-in-and case, so
      // nothing else varies per request.
      tags: { name: "documents?filters", url: "documents?filters" },
    },
  );

  // k6 check/group names may not contain "::" — fixture names quote real
  // label values (e.g. "status::Principal"), so strip it for display only.
  const checkLabel = combination.name.replace(/::/g, ":");

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    [`${checkLabel}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${checkLabel}: response has results array`]: (response: Response) => {
      if (response.status !== 200) return false;
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    [`${checkLabel}: result count matches expectation`]: (
      response: Response,
    ) => {
      if (response.status !== 200) return false;
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      return combination.expectZeroResults
        ? results.length === 0
        : results.length > 0 &&
            results.every(
              (result) =>
                typeof result?.id === "string" &&
                typeof result?.title === "string",
            );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
