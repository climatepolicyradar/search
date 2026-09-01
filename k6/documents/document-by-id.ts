import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

import { BASE_URL, resolveProfile } from "../config.ts";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const documentIds = new SharedArray("document-ids", function () {
  return JSON.parse(open("./fixtures/document-ids.json"));
});

type TDocumentResponse = { data?: { id?: string; title?: unknown } };

// TODO: FUS-356: add a "load" profile here once load-test parameters (VU ramp
// stages, thresholds) are agreed. Select it with `-e PROFILE=load`.
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
  const documentId =
    documentIds[Math.floor(Math.random() * documentIds.length)];
  const res = http.get(`${BASE_URL}/documents/${documentId}`);

  // check() records pass/fail per assertion without stopping the iteration
  // on failure (unlike a thrown error) — failures show up in the run
  // summary as a percentage. A smoke test's bar is 100% checks passing.
  // https://grafana.com/docs/k6/latest/using-k6/checks/
  check(res, {
    "status is 200": (response: Response) => response.status === 200,
    "response has matching data.id": (response: Response) => {
      const body = response.json() as TDocumentResponse;
      return body?.data?.id === documentId;
    },
    "response has data.title": (response: Response) => {
      const body = response.json() as TDocumentResponse;
      return (
        typeof body?.data?.title === "string" && body.data.title.length > 0
      );
    },
  });

  // Paces iterations so VUs don't hammer the endpoint back-to-back with
  // zero delay — standard for smoke/load tests, mimics real user think time.
  sleep(1);
}
