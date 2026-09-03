import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
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
    return JSON.parse(open("./fixtures/filter-combinations.json"));
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
    // ramp to 50 VUs in 3 steps (10/25/50), holding briefly at each rather
    // than jumping straight to peak, so a capacity cliff shows up as a clear
    // step change tied to a specific VU count instead of an ambiguous
    // average over the whole run. /search/passages is a single Vespa query
    // with a 5s timeout (search/engines/dev_vespa.py:1363) — a `filters`
    // clause adds YQL predicates to that same query rather than triggering
    // extra Vespa calls (unlike /documents?fields=), so there is no
    // fan-out-maximising combination to chase the way fields-combinations.ts
    // does. Load mode instead fixes the request to the fixture's most
    // structurally complex real shape (the nested or-in-and) as the closest
    // available proxy for "most expensive single query", rather than
    // sweeping all combinations, so a threshold breach is attributable to
    // one specific request shape. Same VU ramp as index.ts (FUS-358) and
    // documents/{document_id}/index.ts (FUS-356).
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
  const res = http.get(
    `${BASE_URL}/passages?query=climate&filters=${filtersParam}`,
  );

  // k6 check/group names may not contain "::" — fixture names quote real
  // label values (e.g. "concept::Q557"), so strip it for display only.
  const checkLabel = combination.name.replace(/::/g, ":");

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
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
      const results = body?.results ?? [];
      return combination.expectZeroResults
        ? results.length === 0
        : results.length > 0 &&
            results.every(
              (result) =>
                typeof result?.text_block_id === "string" &&
                typeof result?.document_id === "string",
            );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
