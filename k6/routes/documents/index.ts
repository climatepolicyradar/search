import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const searchQueries = new SharedArray("search-queries", function () {
  return JSON.parse(open("./fixtures/search-queries.json"));
});

type TDocumentResult = { id?: unknown; title?: unknown };
type TSearchResponse = { results?: TDocumentResult[] };

// TODO: FUS-357: add a "load" profile here once load-test parameters (VU ramp
// stages, thresholds) are agreed, using the worst-case combination (filters +
// both `fields` values together). Select it with `-e PROFILE=load`.
const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
};

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = resolveProfile("documents: base query", PROFILES);

// k6 calls this function once per VU iteration for the whole run.
export default function () {
  const query = searchQueries[Math.floor(Math.random() * searchQueries.length)];
  const res = http.get(
    `${BASE_URL}/documents?query=${encodeURIComponent(query)}`,
  );

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    "status is 200": (response: Response) => response.status === 200,
    "response has results array": (response: Response) => {
      const body = response.json() as TSearchResponse;
      return Array.isArray(body?.results);
    },
    "results have id and title": (response: Response) => {
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
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
