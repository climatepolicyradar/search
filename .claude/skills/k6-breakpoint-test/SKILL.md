---
name: k6-breakpoint-test
description:
  Use when asked to run a breakpoint/capacity load test against search-api, find
  real numbers for k6 load thresholds, or refresh k6/docs/results/ — covers
  running k6/tests/breakpoint/'s constant-arrival-rate ladder, cross-checking
  with AWS metrics, and proposing k6/tests/smoke-load/routes/** threshold
  changes
---

# k6 Breakpoint Test Workflow

## Overview

Runs `k6/tests/breakpoint/`'s arrival-rate ladder against production search-api
to find the real healthy/collapse boundary, corroborates it with AWS metrics,
writes up a dated results file from the template, and proposes (never silently
applies) threshold changes to `k6/tests/smoke-load/routes/**`.

**REQUIRED READING FIRST:** `k6/docs/load-threshold-methodology.md` — this skill
is the executable version of that method. If the two disagree, the methodology
doc is the source of truth; update it, don't just patch this skill.

## Step 1 — Confirm scope with the user before sending any traffic

This fires real load at production (`api.climatepolicyradar.org/search`) and
will deliberately push it past its breaking point. Before running anything:

1. State the plan (steps/multipliers, estimated duration, which routes).
2. Get explicit confirmation. Do not treat a prior approval in the conversation
   as blanket consent for a new run — ask again for this run.
3. If credentials or `.env` (`VESPA_ENDPOINT`/`VESPA_READ_TOKEN`) aren't set up,
   say so and stop rather than guessing values.

## Step 2 — Prerequisites check

```bash
cd k6/tests/breakpoint
just check   # Vespa access, AWS identity, k6 type-check
```

Fix anything that fails before proceeding — don't burn a run window on a broken
harness.

## Step 3 — Get a real traffic baseline

```bash
AWS_PROFILE=production uv run python baseline.py
```

Anchor the ladder's steps low, around where the system is expected to break, not
on the reported peak — see Known Limitations below.

## Step 4 — Run the ladder

```bash
k6 run -e BASELINE_RPS=<n> -e STEPS=<comma-separated multipliers> \
  -e CACHE_MODE=bust --out json=results/run.json \
  --summary-export=results/summary.json load.ts
```

Record the exact start time (UTC) before launching — needed for step 5. Run in
the background; a 4+ step ladder with 5-minute holds per step takes 15-30+
minutes and commonly auto-aborts partway (expected — the abort threshold IS the
"found the cliff" signal, not a failure of the run).

## Step 5 — Pull AWS metrics for the same window

```bash
AWS_PROFILE=production uv run python metrics_aws.py \
  --start <run-start-utc> --end <run-end-plus-a-few-min> \
  --load-balancer app/ecs-express-gateway-alb-b0a18abd/460db4bc905aacb6 \
  --out results/aws.json
```

Pad the end time a couple of minutes past the run's actual end — CloudWatch
lags.

## Step 6 — Write up the dated results file

Copy `results-template.md` (in this skill's directory) to
`k6/docs/results/{{YYYY-MM-DD}}-breakpoint-test-baseline.md` and fill it in from
the k6 summary + AWS metrics. Do not put numbers anywhere except this dated file
— see Known Limitations.

## Step 7 — Propose threshold changes; do not auto-apply

For each `k6/tests/smoke-load/routes/**` file with a `load` profile, compare its
current `http_req_duration: ["p(95)<Nms"]` against this run's measured
healthy-ceiling / collapse-point boundary. Write the proposal into the results
file's "Threshold changes proposed" section, then separately show the user a
diff of any file you'd change. **Wait for explicit confirmation before editing
any `k6/tests/smoke-load/routes/**` file\*\* — this applies even if the measured
cliff looks close to what's already there. Never auto-apply.

If a threshold value itself changes (not just the comment/citation), also update
the citation comment in that file to point at the new dated results file.

## Known Limitations (don't re-discover these)

- **A response-time number from one load condition is not valid at another.**
  Using a "healthy" route's p95 from an earlier _stressed_ run as input to a
  different scenario's arithmetic produces a wrong answer that still looks
  plausible. Always use the response time actually measured under the load
  condition you're reasoning about, not a number carried over from a different
  step or a different run.
- **`ramping-vus` self-throttles.** Each VU loops request → `sleep()` → repeat,
  so its offered rate is `VUs / (response_time + sleep_time)`. As response time
  rises, offered load silently falls — so a fixed VU count can look "fine"
  purely because the system's own slowness is suppressing the load, not because
  it's actually handling that VU count well. Never trust a `ramping-vus` result
  as a capacity number; only `constant-arrival-rate` (what `load.ts` uses) holds
  offered RPS constant regardless of response time.
- **A `p(95)` of exactly `1m0s` is k6's request timeout, not a measurement.**
  k6's default `http.timeout` is 60s. A step reporting `p(95)=1m0s`/`p(99)=1m0s`
  means requests were hitting that ceiling, not that the true response time was
  exactly 60 seconds — treat it as "at least 60s or hung."
- **CloudFront caches search responses on the full query string.** Any route
  cycling through a small, fixed set of query/filter/ID values (as
  `k6/tests/smoke-load/routes/**`'s `load` profiles do — as few as 1 to 5
  distinct values) will be served almost entirely by the edge after the first
  hit unless every request carries a unique cache-busting parameter. Verified
  directly: the same request shape and VU count measured 108ms p95 uncached vs
  8.76s p95 cache-busted — an ~80x difference from caching alone. Before
  trusting _any_ `k6/tests/smoke-load/routes/**` `load` profile result, confirm
  its default function still cache-busts (`_cb` param present when
  `PROFILE=load`); if a new route/file is added without one, its "load test"
  numbers will describe CloudFront, not search-api.
- **Zero `http_req_failed` does not mean healthy.** A route can report 0% errors
  while still being unusable (e.g. p95 of 8-9 seconds) — `0% http_req_failed`
  only means nothing hit a hard failure/timeout, not that latency was
  acceptable. Always read alongside `http_req_duration`.
- **Anchor the ladder low, not on peak traffic.** `baseline.py`'s peak-minute
  RPS is an upper bound on _all_ traffic to that load balancer, not just search,
  and can be an order of magnitude above where search-api actually breaks. A
  ladder anchored on peak spends every step past the cliff and measures nothing.
  Anchor near where a prior run (or `k6/docs/results/`'s most recent file) found
  the boundary, and widen from there.
- **The run frequently auto-aborts partway — that's the intended signal, not a
  bug.** `http_req_failed` thresholds have `abortOnFail: true` so the harness
  stops rather than sustaining a broken system for the rest of the ladder. A
  later step (e.g. 8x) showing `0s`/no traffic sent means the run never reached
  it, not that it was healthy — don't report it as a measurement.
- **Vespa metrics are optional for finding the cliff, required for explaining
  it.** `metrics_vespa.py`/`VESPA_ENDPOINT`/`VESPA_READ_TOKEN` are not needed
  just to determine _where_ the ceiling is — that comes from the k6 summary
  alone. They matter when diagnosing _why_ (is Vespa's 40-concurrent-search
  ceiling involved, or is it purely the API task).

## Quick Reference

| Question                                    | Where to look                                                                                                         |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Is this route's load profile cache-busting? | grep the file's default function for `_cb` or `cacheBuster`, gated on `PROFILE=load`                                  |
| What was the last measured cliff?           | Most recent file in `k6/docs/results/`                                                                                |
| Did autoscaling fire during the failure?    | `metrics_aws.py` output, `RunningTaskCount` series                                                                    |
| Was the bottleneck CPU or something else?   | `metrics_aws.py`, `CpuUtilized` — pinned high = CPU-bound; low/dropping during failure = thread/connection-pool bound |
| Full step-by-step method                    | `k6/docs/load-threshold-methodology.md`                                                                               |
