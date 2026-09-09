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

// SharedArray shares this data once across all VUs instead of every VU
// holding its own copy in memory.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
//
// `filters` is free-form JSON not enumerated in the OpenAPI schema, so these
// combinations are sourced from real usage, not guessed: the shape matches
// search-api's Filter/FieldFilter/AttributesCondition models
// (search/engines/dev_vespa.py, see SimpleExampleFilter/ComplexExampleFilter
// there) and is exactly what navigator-frontend sends as the `filters` param
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
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(
  "documents: filter combinations",
  PROFILES,
);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    filterCombinations[Math.floor(Math.random() * filterCombinations.length)];
  const filtersParam = encodeURIComponent(JSON.stringify(combination.filters));
  const res = http.get(`${BASE_URL}/documents?filters=${filtersParam}`);

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
                typeof result?.id === "string" &&
                typeof result?.title === "string",
            );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(SLEEP_SECONDS);
}
