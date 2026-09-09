# Deriving k6 load thresholds from measured capacity

How to (re-)establish what `http_req_duration` / `http_req_failed` values belong
in a route's `load` profile, instead of guessing or reusing a route-agnostic
dashboard line.

## Why this exists

The `load` profile thresholds in `k6/routes/**` used to cite a "2s p95 line on
the vespa-search dashboard" from the Fusion monitoring RFC — but that RFC
explicitly deferred formalising it as a real SLO, so the number was a guess, not
a measurement. This doc is the repeatable method for replacing that guess with
something backed by evidence, without baking specific numbers into code comments
(see `k6/docs/results/` for dated results from past runs — this file only covers
method).

## Prerequisites

- `pre-launch-perf/` in this repo (the standalone capacity-testing harness — see
  its own README for setup). It is intentionally not wired into `k6/`, so it can
  be run without affecting the routine test suite.
- Production AWS credentials (`aws login`, profile `production`), for CloudWatch
  and the live traffic baseline.
- `VESPA_ENDPOINT` / `VESPA_READ_TOKEN`, if also diagnosing _why_ a breakpoint
  occurs (not required just to find the breakpoint itself).

## Method

1. **Get a real traffic baseline.** `just baseline` (in `pre-launch-perf/`)
   reads CloudWatch ALB `RequestCount` for the live traffic load balancer and
   reports median/p95/peak-minute RPS. This anchors the load ladder in reality
   rather than an arbitrary starting point.

2. **Run a capacity ladder with `constant-arrival-rate`, not `ramping-vus`.** A
   VU-driven test self-throttles: as latency rises each VU completes fewer
   iterations, so offered load falls right when the system is struggling, which
   hides the failure curve. Arrival-rate holds offered RPS regardless of
   response time, so the cliff is actually visible. `pre-launch-perf`'s
   `load.ts` does this, stepping through multipliers of the baseline
   (`just run <baseline_rps> "<steps>"`).

   Anchor low and widen brackets around where things are expected to break,
   rather than starting from the peak-traffic baseline — a ladder anchored too
   high spends every step past the cliff and describes nothing.

3. **Cache-bust every request.** CloudFront sits in front of search-api and
   caches responses on the full query string. A run without a cache-buster
   measures the edge, not the origin — confirmed directly: the same request
   shape at the same concurrency measured 108ms p95 uncached vs 8.76s p95
   cache-busted. `CACHE_MODE=bust` (the default) appends a unique parameter per
   request so every request reaches origin. Only a `bust` run produces a valid
   capacity number; a `realistic` run measures user-facing latency with caching,
   which is a different (also useful, but not this) question.

4. **Read the step-by-step summary, not just the aggregate.** Each step's
   `http_req_duration{step:...,route:...}` and `http_req_failed{step:...}` show
   whether that step was healthy or collapsed. Look for the boundary: the last
   step where error rate stays near zero and no route is hitting k6's 60s
   default request timeout (a `p(95)` reported as exactly `1m0s` is that
   timeout, not a real measured response time — treat it as "at least 60s or
   hung", not a precise number).

5. **Corroborate with server-side metrics**, via `pre-launch-perf`'s
   `metrics_aws.py` for the same time window (ECS task count, CPU, ALB
   `TargetResponseTime`) and optionally `metrics_vespa.py` if Vespa is a
   suspect. This distinguishes an autoscaling/CPU-bound failure from a
   thread-pool/connection-pool failure, which have different fixes and different
   implications for whether the number is stable over time.

6. **Set the threshold above the last healthy step, below the collapse.** The
   exact value matters less than getting the right side of the cliff — in
   practice the gap between "healthy" and "collapsed" tends to be large (an
   order of magnitude or more), not a fine boundary to tune precisely. A looser
   threshold with headroom for run-to-run variance is preferable to a tight one
   that flags on noise, given this is derived from a single run's worth of data
   unless repeated.

7. **Record the results in a new dated file** under `k6/docs/results/` (method
   only lives here; numbers live there) and reference that file, not inline
   numbers, from the `load` profile's threshold comment in `k6/routes/**`. This
   keeps the code comment stable as thresholds are re-derived over time, rather
   than needing an edit every time a number is refreshed.

## When to re-run this

- Before a launch or any change expected to affect capacity (task sizing,
  autoscaling policy, Vespa cluster changes, request-handling code such as
  connection pooling or thread pool sizing).
- If a `load` profile starts failing in CI/Cloud without a clear code regression
  — the threshold may be stale relative to current infrastructure, not the code
  being wrong.
- Periodically, since infrastructure and traffic patterns drift; there is no
  fixed cadence yet — use judgement.
