import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const documentIds = new SharedArray("document-ids", function () {
  return JSON.parse(open("./fixtures/document-ids.json"));
});

const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

type TDocumentResponse = { data?: { id?: string; title?: unknown } };

// FUS-356: add a "load" profile here once load-test parameters (VU ramp
// stages, thresholds) are agreed. Select it with `-e PROFILE=load`.
const PROFILES = {
  smoke: {
    vus: 5,
    duration: "1m",
  },
};

type TProfileName = keyof typeof PROFILES;

const profileName = (__ENV.PROFILE || "smoke") as TProfileName;

export const options = PROFILES[profileName];

export default function () {
  const documentId =
    documentIds[Math.floor(Math.random() * documentIds.length)];
  const res = http.get(`${BASE_URL}/documents/${documentId}`);

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

  sleep(1);
}
