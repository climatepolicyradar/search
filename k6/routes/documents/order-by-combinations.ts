import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
//
// Confirmed via the production OpenAPI schema
// (https://api.climatepolicyradar.org/search/openapi.json): three sortable
// fields (relevance, attributes.published_date, title), each asc/desc — 6
// combinations. `relevance desc` doubles as the API's default order_by, so
// it's flagged `isDefault` rather than tested as a separate 7th request.
// `relevance` has no externally-verifiable deterministic order, so only the
// `published_date`/`title` cases assert actual sort order; all cases assert
// the request succeeds with well-formed results.
type TOrderByCombination = {
  orderBy: string;
  isDefault: boolean;
  sortField: "published_date" | "title" | null;
  sortDirection: "asc" | "desc" | null;
};

const orderByCombinations = new SharedArray(
  "order-by-combinations",
  function (): TOrderByCombination[] {
    return JSON.parse(open("./fixtures/order-by-combinations.json"));
  },
);

type TDocumentResult = {
  id?: unknown;
  title?: unknown;
  attributes?: { published_date?: unknown };
};
type TSearchResponse = { results?: TDocumentResult[] };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(PROFILES);

function isSorted(
  results: TDocumentResult[],
  field: "published_date" | "title",
  direction: "asc" | "desc",
): boolean {
  const values = results.map((result) =>
    field === "title"
      ? String(result.title ?? "").toLowerCase()
      : String(result.attributes?.published_date ?? ""),
  );
  for (let i = 1; i < values.length; i++) {
    const comparison = values[i - 1].localeCompare(values[i]);
    if (direction === "asc" ? comparison > 0 : comparison < 0) {
      return false;
    }
  }
  return true;
}

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    orderByCombinations[Math.floor(Math.random() * orderByCombinations.length)];
  // Fixed, broad query: this test is about order_by behaviour, not query
  // relevance — a query with a large, stable result set keeps runs
  // comparable across iterations and profiles.
  const res = http.get(
    `${BASE_URL}/documents?query=climate&order_by=${encodeURIComponent(combination.orderBy)}`,
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    [`${combination.orderBy}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${combination.orderBy}: results have id and title`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      return (
        results.length > 0 &&
        results.every(
          (result) =>
            typeof result?.id === "string" && typeof result?.title === "string",
        )
      );
    },
    [`${combination.orderBy}: results are sorted`]: (response: Response) => {
      if (
        combination.sortField === null ||
        combination.sortDirection === null
      ) {
        return true;
      }
      const body = response.json() as TSearchResponse;
      return isSorted(
        body?.results ?? [],
        combination.sortField,
        combination.sortDirection,
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
