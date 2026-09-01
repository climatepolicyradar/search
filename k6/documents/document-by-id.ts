import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

// SharedArray loads this JSON file once and shares it across all VUs
// (see below), instead of every VU parsing its own copy in memory.
// Required for any array data read in k6's init context.
// https://grafana.com/docs/k6/latest/javascript-api/k6-data/sharedarray/
const documentIds = new SharedArray("document-ids", function () {
  return JSON.parse(open("./fixtures/document-ids.json"));
});

// __ENV reads a variable passed on the command line, e.g. `-e BASE_URL=...`.
// Defaults to production so `k6 run` works out of the box with no setup.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/environment-variables/
const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

type TDocumentResponse = { data?: { id?: string; title?: unknown } };

// A VU ("virtual user") is one simulated concurrent user — it runs the
// default-exported function below in a loop for `duration`. `options`
// (below) configures how many VUs run and for how long.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/
//
// TODO: FUS-356: add a "load" profile here once load-test parameters (VU ramp
// stages, thresholds) are agreed. Select it with `-e PROFILE=load`.
const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
};

type TProfileName = keyof typeof PROFILES;

const profileName = (__ENV.PROFILE || "smoke") as TProfileName;

// k6 requires `options` to be a named export — this is how it reads VU/
// duration config for the run, not a convention we chose.
export const options = PROFILES[profileName];

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
