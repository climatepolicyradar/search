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
// (https://api.climatepolicyradar.org/search/openapi.json): two sortable
// fields (relevance, idx), each asc/desc — 4 combinations, all covered here
// per FUS-350's scope (the documents story's separate "default" flag doesn't
// apply the same way: `idx asc` IS the default here, so it's both the first
// fixture entry and flagged `isDefault` rather than a 5th separate case).
// `idx asc` is what the base query (FUS-348) already exercises unset — this
// file additionally requests it explicitly to confirm the param round-trips.
// `relevance` has no externally-verifiable deterministic order, so only the
// `idx` cases assert actual sort order; all cases assert the request
// succeeds with well-formed results. Verified live:
// `relevance asc` returns results identical to `relevance desc`, matching
// `_ranking_overrides_for_passage_order_by`'s behaviour
// (search/engines/dev_vespa.py) of falling back to `relevance` (desc)
// ranking with a warning rather than erroring — asc is accepted but not
// actually a distinct ordering, so this is asserted explicitly rather than
// glossed over as "just another combination".
type TOrderByCombination = {
  orderBy: string;
  isDefault: boolean;
  sortField: "idx" | null;
  sortDirection: "asc" | "desc" | null;
};

const orderByCombinations = new SharedArray(
  "order-by-combinations",
  function (): TOrderByCombination[] {
    return JSON.parse(open("./fixtures/order-by-combinations.json"));
  },
);

// `idx` only orders passages within a single document (confirmed live:
// without a document_id filter, results are grouped by relevance first, and
// `idx` is not a meaningful global sort key) — so this test fixes the query
// to a single, stable document with a large passage count (629 passages at
// time of writing) rather than the documents story's broad free-text query.
const FIXED_DOCUMENT_ID = "CCLW.document.i00007398.n0000";
const FIXED_FILTERS = encodeURIComponent(
  JSON.stringify({
    op: "and",
    filters: [
      { field: "document_id", op: "contains", value: FIXED_DOCUMENT_ID },
    ],
  }),
);

type TPassageResult = {
  text_block_id?: unknown;
  document_id?: unknown;
  idx?: unknown;
};
type TSearchResponse = { results?: TPassageResult[] };

const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile(
  "passages: order_by combinations",
  PROFILES,
);

function isSorted(
  results: TPassageResult[],
  direction: "asc" | "desc",
): boolean {
  const values = results.map((result) => Number(result.idx ?? 0));
  for (let i = 1; i < values.length; i++) {
    if (
      direction === "asc"
        ? values[i - 1] > values[i]
        : values[i - 1] < values[i]
    ) {
      return false;
    }
  }
  return true;
}

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination =
    orderByCombinations[Math.floor(Math.random() * orderByCombinations.length)];
  const res = http.get(
    `${BASE_URL}/passages?query=climate&filters=${FIXED_FILTERS}&order_by=${encodeURIComponent(combination.orderBy)}`,
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    [`${combination.orderBy}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${combination.orderBy}: results have text_block_id and document_id`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      return (
        results.length > 0 &&
        results.every(
          (result) =>
            typeof result?.text_block_id === "string" &&
            typeof result?.document_id === "string",
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
      return isSorted(body?.results ?? [], combination.sortDirection);
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
