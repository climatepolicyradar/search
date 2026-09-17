// Five expensive /search/documents shapes, run against a locally-served API
// backed by the local Vespa container, reported as one small table.
//
// Every shape here is lifted from the existing suite in ../../k6 rather than
// invented, so a number measured locally is measuring the same request the
// smoke/load tests and the breakpoint ladder measure in production:
//
//   fan-out      ../../k6/tests/breakpoint/load.ts            (documents())
//   filters      ../../k6/tests/smoke-load/routes/documents/filter-combinations.ts
//   order-by     ../../k6/tests/smoke-load/routes/documents/order-by-combinations.ts
//   deep-page    ../../k6/tests/smoke-load/routes/documents/pagination-combinations.ts
//   large-page   ../../k6/tests/smoke-load/routes/documents/pagination-combinations.ts
//
// Only /search/documents is covered: `just feed-documents` feeds the documents
// schema, so /search/passages and /search/labels would be querying empty
// content clusters locally and timing nothing.
//
//   just perf-test         # 5 VUs, 30s
//   just perf-test 20 2m   # just takes positional args, not vus=20
import http, { type Response } from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/search";

// This script exists to hammer a laptop, and its defaults (no think time at
// higher VU counts, deep pagination, 100-hit pages full of large `passages`
// summaries) are not something to point at a shared environment by accident.
// A stray BASE_URL in the shell should fail the run, not aim it at production.
const host = BASE_URL.replace(/^https?:\/\//, "")
  .split("/")[0]
  .split(":")[0];
if (host !== "localhost" && host !== "127.0.0.1") {
  throw new Error(
    `Refusing to run: BASE_URL host ${host} is not local. This is a local ` +
      `perf harness — use ../../k6 for anything deployed.`,
  );
}

const VUS = Number(__ENV.VUS ?? 5);
const DURATION = __ENV.DURATION || "30s";
// Think time between a VU's passes over the five shapes. 0 by default: this is
// a capacity probe against a container on the same machine, not a simulation
// of real users, and the numbers wanted are "how long does this query take
// when the box is busy".
const SLEEP_SECONDS = Number(__ENV.SLEEP_SECONDS ?? 0);

// The three-clause `and` from filter-combinations.ts's "combined filters" case,
// which breakpoint/load.ts also reuses as its documents filter.
const COMBINED_FILTERS = {
  op: "and",
  filters: [
    { field: "labels.value.id", op: "contains", value: "category::Report" },
    { field: "labels.value.id", op: "contains", value: "status::Principal" },
    {
      field: "attributes.published_date",
      key: "published_date",
      op: "gte",
      value: "2015-01-01T00:00:00.000Z",
    },
  ],
};

// filter-combinations.ts's nested or-in-and — the shape navigator-frontend
// sends for a multi-select within a facet, and the one its load profile picks
// as the most structurally complex real request.
const NESTED_FILTERS = {
  op: "and",
  filters: [
    {
      op: "or",
      filters: [
        { field: "labels.value.id", op: "contains", value: "category::Law" },
        { field: "labels.value.id", op: "contains", value: "category::Policy" },
      ],
    },
    { field: "labels.value.id", op: "contains", value: "status::Principal" },
  ],
};

const FACET_FIELDS =
  "fields=facets.labels.value.type&fields=facets.labels.type";

type TQuery = { name: string; why: string; path: string };

const QUERIES: TQuery[] = [
  {
    name: "fan-out",
    why: "both facets + filters: up to 8 concurrent Vespa queries per request",
    path:
      `/documents?query=climate+adaptation&${FACET_FIELDS}` +
      `&filters=${encodeURIComponent(JSON.stringify(COMBINED_FILTERS))}` +
      `&page_size=10`,
  },
  {
    name: "nested-filters",
    why: "nested or-in-and, the most complex real filter shape",
    path: `/documents?query=climate&filters=${encodeURIComponent(
      JSON.stringify(NESTED_FILTERS),
    )}`,
  },
  {
    name: "order-by",
    why: "sort by attribute rather than relevance",
    path: `/documents?query=climate&order_by=${encodeURIComponent(
      "attributes.published_date desc",
    )}`,
  },
  {
    name: "deep-page",
    why: "offset 490 — cost of Vespa skipping ranked hits",
    path: `/documents?query=climate&page_token=50&page_size=10`,
  },
  {
    name: "large-page",
    why: "100 hits of summaries — the shape the big-passages corpus stresses",
    path: `/documents?query=climate&page_token=1&page_size=100`,
  },
];

// k6 metric names allow only letters, numbers and underscores, so the hyphens
// in the shape names above cannot be carried through verbatim.
function metricName(queryName: string): string {
  return `q_${queryName.replace(/-/g, "_")}`;
}

// One Trend per shape rather than reading tagged sub-metrics of
// http_req_duration: k6 only surfaces a tagged sub-metric in the summary if a
// threshold is declared on it, and declaring five thresholds purely to make
// five numbers printable is a worse trade than five explicit metrics.
const durations: Record<string, Trend> = {};
for (const query of QUERIES) {
  durations[query.name] = new Trend(metricName(query.name), true);
}

export const options = {
  vus: VUS,
  duration: DURATION,
  // `count` is what makes the per-shape row meaningful — a p95 over three
  // samples is noise, and the table should show you that it is.
  summaryTrendStats: ["med", "p(95)", "max", "count"],
  // Not a performance bar: a non-200 locally means the stack is wrong (Vespa
  // down, app not deployed, corpus not fed), and the run's timings are then
  // worthless. Exit non-zero so that is not mistaken for a result.
  thresholds: { checks: ["rate==1.00"] },
};

// One iteration walks all five shapes, so every shape gets the same number of
// samples and the rows are directly comparable.
export default function (): void {
  for (const query of QUERIES) {
    const res = http.get(`${BASE_URL}${query.path}`, {
      tags: { name: `documents:${query.name}` },
    });
    durations[query.name].add(res.timings.duration);
    check(res, {
      [`${query.name}: status is 200`]: (response: Response) =>
        response.status === 200,
      [`${query.name}: response has results array`]: (response: Response) =>
        Array.isArray((response.json() as { results?: unknown[] })?.results),
    });
  }
  if (SLEEP_SECONDS > 0) sleep(SLEEP_SECONDS);
}

type TMetric = { values: Record<string, number> };
type TSummary = { metrics: Record<string, TMetric> };

function ms(value: number | undefined): string {
  return value === undefined ? "-" : `${value.toFixed(0)}ms`;
}

function pad(value: string, width: number): string {
  return value.length >= width
    ? value
    : value + " ".repeat(width - value.length);
}

function padLeft(value: string, width: number): string {
  return value.length >= width
    ? value
    : " ".repeat(width - value.length) + value;
}

// Replaces k6's default end-of-test summary with just the numbers asked for.
// https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/
export function handleSummary(data: TSummary): Record<string, string> {
  const nameWidth = Math.max(...QUERIES.map((q) => q.name.length)) + 2;
  const lines = [
    "",
    `local perf — ${VUS} VUs, ${DURATION}, ${BASE_URL}`,
    "",
    pad("query", nameWidth) +
      padLeft("reqs", 7) +
      padLeft("med", 10) +
      padLeft("p95", 10) +
      padLeft("max", 10) +
      "   why",
    "-".repeat(nameWidth + 37 + 4),
  ];

  for (const query of QUERIES) {
    const values = data.metrics[metricName(query.name)]?.values ?? {};
    lines.push(
      pad(query.name, nameWidth) +
        padLeft(String(values["count"] ?? 0), 7) +
        padLeft(ms(values["med"]), 10) +
        padLeft(ms(values["p(95)"]), 10) +
        padLeft(ms(values["max"]), 10) +
        `   ${query.why}`,
    );
  }

  const reqs = data.metrics["http_reqs"]?.values ?? {};
  const failed = data.metrics["http_req_failed"]?.values ?? {};
  const checks = data.metrics["checks"]?.values ?? {};
  lines.push(
    "-".repeat(nameWidth + 37 + 4),
    `total ${(reqs["count"] ?? 0).toFixed(0)} requests at ` +
      `${(reqs["rate"] ?? 0).toFixed(1)} req/s — ` +
      `${((failed["rate"] ?? 0) * 100).toFixed(2)}% failed, ` +
      `${((checks["rate"] ?? 0) * 100).toFixed(2)}% checks passed`,
    "",
  );

  return { stdout: lines.join("\n") };
}
