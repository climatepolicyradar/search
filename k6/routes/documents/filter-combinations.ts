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
    return JSON.parse(open("./fixtures/filter-combinations.json"));
  },
);

type TDocumentResult = { id?: unknown; title?: unknown };
type TSearchResponse = { results?: TDocumentResult[]; total_size?: number };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
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
  sleep(1);
}
