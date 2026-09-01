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
// both together — the worst-case fan-out combination, and the target for
// this script's eventual load-test graduation (FUS-357).
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
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(PROFILES);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    fieldsCombinations[Math.floor(Math.random() * fieldsCombinations.length)];
  // `fields` is a repeated query param (confirmed against the live API), not
  // a single comma-separated value.
  const fieldsQuery = combination.fields
    .map((field) => `fields=${encodeURIComponent(field)}`)
    .join("&");
  const res = http.get(
    `${BASE_URL}/documents?query=climate${fieldsQuery ? `&${fieldsQuery}` : ""}`,
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
