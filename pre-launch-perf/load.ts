// Stepped load test for search-api, to find the level at which it breaks
// before the 2026-09-14 launch.
//
// Deliberately self-contained: it does NOT import from ../k6/config.ts, so
// nothing under k6/ has to change and this can't break when that file does.
// Request shapes are copied from the k6/routes/**/fixtures/ files, which are
// already known to return 200s against production.
//
// Run:
//   k6 run -e BASELINE_RPS=<peak-minute rps from baseline.py> load.ts
//
// See README.md for the full procedure.

import http from "k6/http";
import { check } from "k6";

// --- Target -----------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

// A stray BASE_URL in a shell must not be able to aim a 5x arrival-rate ramp
// at another service — in particular not at navigator-backend, which still
// serves all live search traffic. Throwing here happens in init context, before
// a single request is sent. k6's runtime has no URL global, hence the regex.
const ALLOWED_HOSTS = ["api.climatepolicyradar.org", "localhost", "127.0.0.1"];
const targetHost = BASE_URL.replace(/^https?:\/\//, "")
  .split("/")[0]
  .split(":")[0];
if (!ALLOWED_HOSTS.includes(targetHost)) {
  throw new Error(
    `Refusing to run: BASE_URL host ${targetHost} is not in the allow-list ` +
      `(${ALLOWED_HOSTS.join(", ")}). This test only ever targets search-api.`,
  );
}

// --- Load shape -------------------------------------------------------------

// Peak-minute RPS of live search traffic, from baseline.py. Not the mean —
// provisioning is sized on peak. No default worth guessing, so fail loudly.
const BASELINE_RPS = Number(__ENV.BASELINE_RPS);
if (!Number.isFinite(BASELINE_RPS) || BASELINE_RPS <= 0) {
  throw new Error(
    "BASELINE_RPS must be a positive number, e.g. -e BASELINE_RPS=12. " +
      "Get it from `just baseline`.",
  );
}

// CloudFront sits in front of search-api and DOES cache search responses —
// verified: first request Miss, subsequent identical requests Hit, `age`
// increments. The full query string is part of the cache key (`?_cb=1` and
// `?_cb=2` both Miss; repeating `?_cb=1` Hits).
//
// This matters more than anything else in this file. Repeating a small set of
// query terms means the edge answers most requests and the test measures
// CloudFront, not ECS or Vespa — origin then sees a fraction of the offered
// load. So:
//
//   bust      (default) append a unique `_cb` per request, forcing every
//             request to origin. This is what ECS/Vespa provisioning needs.
//             The API ignores the param — verified identical `total_size` and
//             result count with and without it — so Vespa does the same work.
//   realistic repeat the term pool and let CloudFront serve what it will.
//             Measures what users experience, NOT what the origin must handle.
//
// A `realistic` run is never a capacity result.
const CACHE_MODE = __ENV.CACHE_MODE ?? "bust";
if (CACHE_MODE !== "bust" && CACHE_MODE !== "realistic") {
  throw new Error(
    `CACHE_MODE must be "bust" or "realistic", got "${CACHE_MODE}".`,
  );
}

// Separates this run's cache keys from an earlier run's on the same day. k6
// runs init per VU so this differs per VU, which is fine: it is only ever
// combined with __VU and __ITER, unique within a run.
const RUN_ID = __ENV.RUN_ID ?? Math.random().toString(36).slice(2, 8);

// Multipliers of BASELINE_RPS, run as discrete steps rather than one
// continuous ramp so each load level gets its own cleanly-attributable
// metrics — the run itself then emits the RPS -> p95 -> error-rate table.
const STEPS = (__ENV.STEPS ?? "1,1.5,2,3,5")
  .split(",")
  .map((s) => Number(s.trim()));

// 5 minutes per step. AWS target-tracking re-evaluation plus a fresh Fargate
// task registering healthy behind the load balancer both take a few minutes,
// so a shorter hold measures spike reactivity rather than sustained capacity
// and can complete the whole test on a single task. Same reasoning as the
// comment in k6/routes/passages/index.ts.
const STEP_DURATION_S = Number(__ENV.STEP_DURATION_S ?? 300);
const GRACEFUL_STOP_S = 30;

// Share of traffic per route. ASSUMPTION, not measured — the shape a search
// page view produces. Revisit against PostHog before treating the absolute
// numbers as gospel; the relative ordering is what matters for finding the
// bottleneck.
const ROUTES = [
  { name: "documents", exec: "documents", weight: 0.45 },
  { name: "passages", exec: "passages", weight: 0.3 },
  { name: "labels", exec: "labels", weight: 0.15 },
  { name: "document_by_id", exec: "documentById", weight: 0.1 },
];

const scenarios: Record<string, unknown> = {};
const thresholds: Record<string, unknown> = {
  // Stop at the cliff rather than sustaining a broken system for the
  // remaining steps. delayAbortEval stops a cold-start blip from aborting
  // the run in its first seconds.
  http_req_failed: [
    { threshold: "rate<0.05", abortOnFail: true, delayAbortEval: "30s" },
  ],
};

STEPS.forEach((multiplier, stepIndex) => {
  const step = `${multiplier}x`;
  const startTime = stepIndex * (STEP_DURATION_S + GRACEFUL_STOP_S);

  ROUTES.forEach((route) => {
    // constant-arrival-rate needs an integer `rate`, so a sub-1-rps target
    // has to be expressed by stretching timeUnit instead: 1 per 4s rather
    // than 0.25 per 1s. Without this the per-route floor was 1 rps, i.e. 4 rps
    // total across the four routes -- already past the observed ~4 rps cliff,
    // so the ladder could not describe the healthy region at all.
    const target = BASELINE_RPS * multiplier * route.weight;
    const rate = target >= 1 ? Math.round(target) : 1;
    const timeUnit = target >= 1 ? "1s" : `${Math.round(1 / target)}s`;
    // Concurrency the scenario can reach: offered rate x worst-case seconds
    // per request. The 60s ceiling is k6's default request timeout, which
    // requests do hit once the origin is saturated.
    const perSecond = target >= 1 ? rate : target;

    scenarios[`${route.name}_${step.replace(".", "_")}`] = {
      // constant-arrival-rate, NOT ramping-vus + sleep(). A VU-driven test
      // self-throttles: as latency rises each VU completes fewer iterations,
      // so offered load falls and the breakpoint stays hidden. Arrival-rate
      // holds offered RPS regardless of response time, which is what makes
      // queueing — and therefore the cliff — visible. It also gives us
      // `dropped_iterations` as a direct "can't keep up" signal.
      executor: "constant-arrival-rate",
      exec: route.exec,
      rate,
      timeUnit,
      duration: `${STEP_DURATION_S}s`,
      startTime: `${startTime}s`,
      gracefulStop: `${GRACEFUL_STOP_S}s`,
      preAllocatedVUs: Math.max(5, Math.ceil(perSecond * 5)),
      // A saturated origin pushes requests to k6's 60s default timeout, so
      // sizing on the 5s Vespa timeout under-allocates badly and the run
      // silently under-delivers load. If the summary shows dropped_iterations
      // without matching server errors, raise this and re-run.
      maxVUs: Math.max(50, Math.ceil(perSecond * 60)),
      tags: { step, route: route.name },
    };
  });

  // Tag-keyed, so the summary breaks down per step instead of averaging the
  // healthy early steps together with the broken later ones.
  thresholds[`http_req_duration{step:${step}}`] = ["p(95)<2000"];
  thresholds[`http_req_failed{step:${step}}`] = ["rate<0.01"];

  // Per-route within each step. These exist for the breakdown as much as for
  // the pass/fail: k6 only prints a tagged sub-metric in the summary if some
  // threshold references that tag, and without them a bimodal run (one slow
  // route dragging p95 while the rest sit at ~20ms) is invisible.
  ROUTES.forEach((route) => {
    thresholds[`http_req_duration{step:${step},route:${route.name}}`] = [
      "p(95)<2000",
    ];
  });
});

export const options = {
  scenarios,
  thresholds,
  // We only assert on status, so throwing the bodies away keeps client-side
  // CPU and memory off the critical path — the laptop must not become the
  // bottleneck we end up measuring.
  discardResponseBodies: true,
  summaryTrendStats: ["avg", "min", "med", "p(95)", "p(99)", "max"],
};

// --- Request data -----------------------------------------------------------

// Copied from k6/routes/{documents,passages}/fixtures/search-queries.json.
//
// Caveat worth knowing when reading the results: 5 distinct terms keep their
// posting lists (and, for /passages, its from-disk debug-summary) in the
// content nodes' page cache, so disk I/O is understated versus real traffic.
// relevance_tests/ holds ~102 real production-shaped terms if a more
// cache-hostile run is wanted later — swapping them in is an edit to this
// array and nothing else.
const QUERIES = [
  "climate adaptation",
  "deforestation",
  "carbon pricing",
  "renewable energy",
  "flood risk",
];

// From k6/routes/documents/{document_id}/fixtures/document-ids.json — real,
// pre-verified IDs.
const DOCUMENT_IDS = [
  "CPR.document.i00006774.n0000",
  "Sabin.document.12835.14111",
  "UNFCCC.document.i00002090.n0000",
  "Sabin.document.3703.5490",
];

// The "combined filters: category + status + published_date range (and)" shape
// from k6/routes/documents/fixtures/filter-combinations.json. Two label types
// in the filter is what drives the disjunctive-facet fan-out when combined
// with ?fields= below.
const DOCUMENT_FILTERS = JSON.stringify({
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
});

// The "nested or-in-and" shape from
// k6/routes/passages/fixtures/filter-combinations.json — its most structurally
// complex real combination.
const PASSAGE_FILTERS = JSON.stringify({
  op: "and",
  filters: [
    {
      op: "or",
      filters: [
        {
          field: "document_id",
          op: "contains",
          value: "CCLW.document.i00007398.n0000",
        },
        {
          field: "document_id",
          op: "contains",
          value: "CPR.document.i00006774.n0000",
        },
      ],
    },
    { field: "labels.value.type", op: "contains", value: "concept" },
  ],
});

function pick<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

// A query-string fragment that makes this request's CloudFront cache key
// unique, so it reaches origin. Empty in `realistic` mode.
function cacheBuster(): string {
  if (CACHE_MODE === "realistic") return "";
  return `&_cb=${RUN_ID}-${__VU}-${__ITER}`;
}

// --- Scenario functions -----------------------------------------------------

// The search page shape: free text plus both facet fields. `fields` is what
// drives /documents' fan-out — each value adds concurrent Vespa calls on top
// of the search and the unconditional aggregations query, so with filters
// carrying two label types this is up to 8 Vespa queries per HTTP request
// (api/routers.py:100-130). Half the iterations carry filters, so the step's
// numbers aren't dominated entirely by the worst case.
export function documents(): void {
  const query = encodeURIComponent(pick(QUERIES));
  const fields = "fields=facets.labels.value.type&fields=facets.labels.type";
  const filters =
    Math.random() < 0.5
      ? `&filters=${encodeURIComponent(DOCUMENT_FILTERS)}`
      : "";
  const res = http.get(
    `${BASE_URL}/documents?query=${query}&${fields}${filters}&page_size=10${cacheBuster()}`,
  );
  check(res, { "documents 200": (r) => r.status === 200 });
}

// Single Vespa query, but with the from-disk debug-summary forced on every
// request (dev_vespa.py:1439), so per-hit cost scales with page_size.
export function passages(): void {
  const query = encodeURIComponent(pick(QUERIES));
  const filters =
    Math.random() < 0.3
      ? `&filters=${encodeURIComponent(PASSAGE_FILTERS)}`
      : "";
  const res = http.get(
    `${BASE_URL}/passages?query=${query}${filters}&page_size=10${cacheBuster()}`,
  );
  check(res, { "passages 200": (r) => r.status === 200 });
}

// Filter autocomplete: the frontend sends prefixes as the user types, so send
// a prefix rather than a whole term. Costs 2 Vespa queries — the search plus
// an unbounded whole-corpus grouping whose result the route discards
// (api/routers.py:196).
export function labels(): void {
  const prefix = pick(QUERIES).slice(0, 4);
  const res = http.get(
    `${BASE_URL}/labels?query=${encodeURIComponent(prefix)}&page_size=10${cacheBuster()}`,
  );
  check(res, { "labels 200": (r) => r.status === 200 });
}

// The cheapest route: a document/v1 key-value GET, no fan-out. Useful as a
// control — if this degrades too, the bottleneck is the API or the network
// rather than query cost.
export function documentById(): void {
  // No query string of its own, so the buster leads with `?` rather than `&`.
  const buster = cacheBuster().replace(/^&/, "?");
  const res = http.get(`${BASE_URL}/documents/${pick(DOCUMENT_IDS)}${buster}`);
  check(res, { "document_by_id 200": (r) => r.status === 200 });
}
