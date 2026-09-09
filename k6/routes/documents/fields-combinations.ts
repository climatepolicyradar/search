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
// `fields` is the parameter most directly responsible for /search/documents'
// fan-out cost: each requested facet value triggers an extra concurrent
// Vespa call (search/engines/dev_vespa.py's labels_value_type_facets /
// labels_type_facets, confirmed via the production OpenAPI schema to be the
// only two valid values). Covers no fields (baseline), each field alone, and
// both together — the worst-case fan-out combination.
type TFieldsCombination = {
  name: string;
  fields: string[];
  expectValueType: boolean;
  expectType: boolean;
};

const fieldsCombinations = new SharedArray(
  "fields-combinations",
  function (): TFieldsCombination[] {
    return [
      {
        name: "no fields (baseline)",
        fields: [],
        expectValueType: false,
        expectType: false,
      },
      {
        name: "single field: facets.labels.value.type",
        fields: ["facets.labels.value.type"],
        expectValueType: true,
        expectType: false,
      },
      {
        name: "single field: facets.labels.type",
        fields: ["facets.labels.type"],
        expectValueType: false,
        expectType: true,
      },
      {
        name: "both fields together (worst-case fan-out)",
        fields: ["facets.labels.value.type", "facets.labels.type"],
        expectValueType: true,
        expectType: true,
      },
    ];
  },
);

const searchQueries = new SharedArray("search-queries", function (): string[] {
  return [
    "climate adaptation",
    "deforestation",
    "carbon pricing",
    "renewable energy",
    "flood risk",
  ];
});

// The load profile's fixed worst-case request: both `fields` values (the
// fan-out-maximising combination above) plus a real `filters` shape reused
// from filter-combinations.json's "combined filters" case, rather than the
// smoke sweep's single-param variation — `fields` and `filters` are combined
// independently by search-api (api/routers.py's read_documents), and load
// testing should target the most expensive real request shape, not just the
// most expensive single parameter.
const worstCaseFilters = {
  op: "and",
  filters: [
    { field: "labels.value.id", op: "contains", value: "category::Report" },
    { field: "labels.value.id", op: "contains", value: "status::Principal" },
    {
      field: "attributes.published_date",
      key: "published_date",
      op: "gte",
      value: "2015-01-01T00:00:00.000Z",
    },
  ],
};

type TFacets = {
  "labels.value.type"?: unknown;
  "labels.type"?: unknown;
};
type TSearchResponse = { facets?: TFacets | null };

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
    // ramp outrunning ECS. This route is the expensive one — up to
    // 2 + len(fields) concurrent Vespa calls per request
    // (search/api/routers.py:64,
    // search/engines/dev_vespa.py:782/1002/1165/1228) — so 50 VUs here is a
    // meaningfully heavier load than the same VU count against the cheap
    // single-doc route.
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
    // no baseline data yet"), so treat this as a provisional, not agreed,
    // target until that decision lands. Reused as-is from {document_id}'s
    // graduated threshold (FUS-356) even though this route does more work per
    // request — the RFC figure is a route-agnostic dashboard line, not
    // per-route, so there's no separate number to reference yet.
    // http_req_failed aborts the run early on a failure spike rather than
    // burning the full ramp on a route that's already broken.
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
  "documents: fields combinations",
  PROFILES,
);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  // Smoke mode sweeps all combinations to check correctness; load mode
  // repeats the single worst-case shape (filters + both fields) to find a
  // capacity ceiling for it, per FUS-357's scope — the two profiles are
  // testing different things, not just different volumes of the same thing.
  const combination = isLoadProfile
    ? fieldsCombinations.find((c) => c.expectValueType && c.expectType)!
    : fieldsCombinations[Math.floor(Math.random() * fieldsCombinations.length)];

  const query = searchQueries[Math.floor(Math.random() * searchQueries.length)];
  // `fields` is a repeated query param (confirmed against the live API), not
  // a single comma-separated value.
  const fieldsQuery = combination.fields
    .map((field) => `fields=${encodeURIComponent(field)}`)
    .join("&");
  const filtersQuery = isLoadProfile
    ? `&filters=${encodeURIComponent(JSON.stringify(worstCaseFilters))}`
    : "";
  const res = http.get(
    `${BASE_URL}/documents?query=${encodeURIComponent(query)}${fieldsQuery ? `&${fieldsQuery}` : ""}${filtersQuery}`,
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    [`${combination.name}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${combination.name}: facets match requested fields`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      const facets = body?.facets ?? null;

      if (!combination.expectValueType && !combination.expectType) {
        // No fields requested: facets is entirely absent.
        return facets === null;
      }

      const hasValueType =
        facets?.["labels.value.type"] !== null &&
        facets?.["labels.value.type"] !== undefined;
      const hasType =
        facets?.["labels.type"] !== null &&
        facets?.["labels.type"] !== undefined;
      return (
        hasValueType === combination.expectValueType &&
        hasType === combination.expectType
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
