import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

const documentIds = new SharedArray("document-ids", function () {
  return JSON.parse(open("./fixtures/document-ids.json"));
});

const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

type TDocumentResponse = { data?: { id?: string; title?: unknown } };

export const options = {
  vus: 5,
  duration: "1m",
};

export default function () {
  const documentId =
    documentIds[Math.floor(Math.random() * documentIds.length)];
  const res = http.get(`${BASE_URL}/documents/${documentId}`);

  check(res, {
    "status is 200": (r) => r.status === 200,
    "response has matching data.id": (r) => {
      const body = r.json() as TDocumentResponse;
      return body?.data?.id === documentId;
    },
    "response has data.title": (r) => {
      const body = r.json() as TDocumentResponse;
      return (
        typeof body?.data?.title === "string" && body.data.title.length > 0
      );
    },
  });

  sleep(1);
}
