import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
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
    return JSON.parse(open("./fixtures/fields-combinations.json"));
  },
);

const searchQueries = new SharedArray("search-queries", function (): string[] {
  return JSON.parse(open("./fixtures/search-queries.json"));
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
  },
  load: {
    // ramp to 50 VUs in 3 steps (10/25/50), holding briefly at each rather
    // than jumping straight to peak, so a capacity cliff shows up as a clear
    // step change tied to a specific VU count instead of an ambiguous
    // average over the whole run. Same shape as {document_id}/index.ts
    // (FUS-356), but this route is the expensive one — up to 2 + len(fields)
    // concurrent Vespa calls per request (search/api/routers.py:64,
    // search/engines/dev_vespa.py:782/1002/1165/1228) — so 50 VUs here is a
    // meaningfully heavier load than the same VU count against the cheap
    // single-doc route.
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
export const options = resolveProfile(PROFILES);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const isLoadProfile = __ENV.PROFILE === "load";

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
  sleep(1);
}
