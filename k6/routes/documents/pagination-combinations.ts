import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
//
// `page_token` is a 1-based page number; search-api computes Vespa's offset
// as `(page_token - 1) * page_size` (search/engines/dev_vespa.py). Covers
// the first page (default), a deep page (offset 490 — tests the cost of
// Vespa skipping over ranked results internally), and a large `page_size`.
// The fixed `query=climate` result set (~17k documents at time of writing)
// is large enough that all three cases return full pages.
const paginationCombinations = new SharedArray(
  "pagination-combinations",
  function () {
    return JSON.parse(open("./fixtures/pagination-combinations.json"));
  },
);

type TPaginationCombination = {
  name: string;
  pageToken: number;
  pageSize: number;
  verifyOffsetAdvances: boolean;
};

type TDocumentResult = { id?: unknown; title?: unknown };
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

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const combination = paginationCombinations[
    Math.floor(Math.random() * paginationCombinations.length)
  ] as TPaginationCombination;
  const res = http.get(
    `${BASE_URL}/documents?query=climate&page_token=${combination.pageToken}&page_size=${combination.pageSize}`,
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    [`${combination.name}: status is 200`]: (response: Response) =>
      response.status === 200,
    [`${combination.name}: returns exactly page_size results`]: (
      response: Response,
    ) => {
      const body = response.json() as TSearchResponse;
      const results = body?.results ?? [];
      return (
        results.length === combination.pageSize &&
        results.every(
          (result) =>
            typeof result?.id === "string" && typeof result?.title === "string",
        )
      );
    },
  });

  if (combination.verifyOffsetAdvances) {
    // Proves the offset is actually taking effect, not silently ignored:
    // a deep page must return different documents than page 1.
    const firstPageRes = http.get(
      `${BASE_URL}/documents?query=climate&page_token=1&page_size=${combination.pageSize}`,
    );
    check(firstPageRes, {
      [`${combination.name}: differs from page 1`]: () => {
        const deepPageBody = res.json() as TSearchResponse;
        const firstPageBody = firstPageRes.json() as TSearchResponse;
        const deepPageIds = (deepPageBody?.results ?? []).map((r) => r.id);
        const firstPageIds = (firstPageBody?.results ?? []).map((r) => r.id);
        return JSON.stringify(deepPageIds) !== JSON.stringify(firstPageIds);
      },
    });
  }

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
