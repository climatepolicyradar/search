import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, SLEEP_SECONDS, resolveProfile } from "../../config.ts";

// SharedArray shares this data once across all VUs instead of every VU
// holding its own copy in memory.
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
    return [
      {
        orderBy: "relevance desc",
        isDefault: true,
        sortField: null,
        sortDirection: null,
      },
      {
        orderBy: "relevance asc",
        isDefault: false,
        sortField: null,
        sortDirection: null,
      },
      {
        orderBy: "attributes.published_date desc",
        isDefault: false,
        sortField: "published_date",
        sortDirection: "desc",
      },
      {
        orderBy: "attributes.published_date asc",
        isDefault: false,
        sortField: "published_date",
        sortDirection: "asc",
      },
      {
        orderBy: "title asc",
        isDefault: false,
        sortField: "title",
        sortDirection: "asc",
      },
      {
        orderBy: "title desc",
        isDefault: false,
        sortField: "title",
        sortDirection: "desc",
      },
    ];
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
  "documents: order_by combinations",
  PROFILES,
);

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
  sleep(SLEEP_SECONDS);
}
