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
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(
  "passages: filter combinations",
  PROFILES,
);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    filterCombinations[Math.floor(Math.random() * filterCombinations.length)];
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
