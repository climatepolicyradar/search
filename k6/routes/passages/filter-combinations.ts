import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

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
// load test is scoped) is picked via `-e PROFILE=<name>` (defaulting to
// `smoke`).
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
  const profile = profiles[__ENV.PROFILE || "smoke"] as
    | Record<string, unknown>
    | undefined;
  if (!profile) return profile as unknown as object;
  return { ...profile, cloud: { name: cloudName } };
}

// SharedArray shares this data once across all VUs instead of every VU
// holding its own copy in memory.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
//
// `filters` is free-form JSON not enumerated in the OpenAPI schema, so these
// combinations are sourced from real usage, not guessed: the shape matches
// search-api's Filter/FieldFilter models (search/engines/dev_vespa.py's
// passages_filter_field_to_vespa_field_map / passages_filter_struct_field_to_
// vespa_field_map) and is what navigator-frontend sends as the `filters`
// param for passage search (src/api/passages.ts), always combined with a
// document_id constraint there. Covers a single document_id filter, a single
// labels.value.type filter, both `and`-ed, a nested or-in-and (multiple
// documents `or`-ed, then `and`-ed with a label type — matching
// navigator-frontend's multi-document passage search shape), and a
// zero-result combination — worth testing explicitly since empty-result
// queries can behave very differently under load than populated ones. Unlike
// /documents, passages has no `status::Principal`-style label to build a
// contradictory-filter zero-result case from, so this uses a real document_id
// that has zero indexed passages instead.
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
        name: "single filter: document_id",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              field: "document_id",
              op: "contains",
              value: "CCLW.document.i00007398.n0000",
            },
          ],
        },
      },
      {
        name: "single filter: labels.value.type (concept)",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              field: "labels.value.type",
              op: "contains",
              value: "concept",
            },
          ],
        },
      },
      {
        name: "combined filters: document_id + labels.value.type (and)",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              field: "document_id",
              op: "contains",
              value: "CCLW.document.i00007398.n0000",
            },
            {
              field: "labels.value.type",
              op: "contains",
              value: "concept",
            },
          ],
        },
      },
      {
        name: "combined filters: (document A or document B) and labels.value.type (nested or-in-and)",
        expectZeroResults: false,
        filters: {
          op: "and",
          filters: [
            {
              op: "or",
              filters: [
                {
                  field: "document_id",
                  op: "contains",
                  value: "CCLW.document.i00007398.n0000",
                },
                {
                  field: "document_id",
                  op: "contains",
                  value: "CPR.document.i00006774.n0000",
                },
              ],
            },
            {
              field: "labels.value.type",
              op: "contains",
              value: "concept",
            },
          ],
        },
      },
      {
        name: "zero-result combination: document_id for a real document with no passages",
        expectZeroResults: true,
        filters: {
          op: "and",
          filters: [
            {
              field: "document_id",
              op: "contains",
              value: "Sabin.document.12835.14111",
            },
          ],
        },
      },
    ];
  },
);

type TPassageResult = { text_block_id?: unknown; document_id?: unknown };
type TSearchResponse = { results?: TPassageResult[]; total_size?: number };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
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
    // (search/engines/dev_vespa.py:1363) — a `filters` clause adds YQL
    // predicates to that same query rather than triggering extra Vespa
    // calls (unlike /documents?fields=), so there is no fan-out-maximising
    // combination to chase the way fields-combinations.ts does. Load mode
    // instead fixes the request to the fixture's most structurally complex
    // real shape (the nested or-in-and) as the closest available proxy for
    // "most expensive single query", rather than sweeping all combinations,
    // so a threshold breach is attributable to one specific request shape.
    // Same ramp as index.ts (FUS-358).
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
    // measurements this value is based on. Re-derive (new dated results
    // file, method doc unchanged) rather than editing the number here from
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
  "passages: filter combinations",
  PROFILES,
);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const isLoadProfile = __ENV.PROFILE === "load";

  // Smoke mode sweeps all combinations to check correctness; load mode
  // repeats the single most structurally complex real shape (the nested
  // or-in-and) to find a capacity ceiling for it, per FUS-358's scope — the
  // two profiles are testing different things, not just different volumes of
  // the same thing.
  const combination = isLoadProfile
    ? filterCombinations.find((c) => c.name.includes("nested or-in-and"))!
    : filterCombinations[Math.floor(Math.random() * filterCombinations.length)];
  const filtersParam = encodeURIComponent(JSON.stringify(combination.filters));
  // Load mode always requests the same fixed filter combination, so without
  // a cache-buster it's a single, entirely static URL — CloudFront serves
  // almost every request after the first as a hit, measuring the edge, not
  // origin (see k6/tests/breakpoint/README.md finding 0). Smoke mode sweeps many
  // combinations testing correctness, not capacity, so it's left cacheable.
  const cacheBuster = isLoadProfile
    ? `&_cb=${__VU}-${__ITER}-${Date.now()}`
    : "";
  const res = http.get(
    `${BASE_URL}/passages?query=climate&filters=${filtersParam}${cacheBuster}`,
  );

  // k6 check/group names may not contain "::" — fixture names quote real
  // label values (e.g. "concept::Q557"), so strip it for display only.
  const checkLabel = combination.name.replace(/::/g, ":");

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  //
  // Assertions are deliberately layered — response shape, then result count,
  // then per-result field types are separate named checks rather than one
  // combined boolean. If the response contract regresses (results key
  // renamed, text_block_id changes type, an error body comes back with 200)
  // the failing check name points at which assumption broke, instead of a
  // single opaque "expectation not met".
  check(res, {
    [`${checkLabel}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${checkLabel}: response has results array`]: (response: Response) => {
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    [`${checkLabel}: result count matches expectation`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      if (!Array.isArray(body?.results)) return false;
      return combination.expectZeroResults
        ? body.results.length === 0
        : body.results.length > 0;
    },
    [`${checkLabel}: results have string text_block_id and document_id`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      // Vacuously true for the zero-result case (nothing to check), which is
      // the point — its result count is asserted above.
      return results.every(
        (result) =>
          typeof result?.text_block_id === "string" &&
          typeof result?.document_id === "string",
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
