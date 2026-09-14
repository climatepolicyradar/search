# Breakpoint test baseline — 2026-09-10

Results of applying [the methodology](../load-threshold-methodology.md).
Referenced by the `load` profile thresholds in
`k6/tests/smoke-load/routes/documents/fields-combinations.ts`,
`k6/tests/smoke-load/routes/documents/{document_id}/index.ts`,
`k6/tests/smoke-load/routes/passages/index.ts`, and
`k6/tests/smoke-load/routes/passages/filter-combinations.ts`.

Run against production (`api.climatepolicyradar.org/search`) using
`k6/tests/breakpoint/`, immediately after PR #529 ("fix: update ECS min/max")
was merged and deployed — this run's purpose was to measure the effect of that
change, not to re-derive the baseline from scratch. Confirmed live via
`describe-scalable-targets` before running: `search-api` was at
`MinCapacity=3, MaxCapacity=8` (up from the `min=1, max=4` in place for
[2026-09-09's baseline](2026-09-09-breakpoint-test-baseline.md)), with 3 tasks
already running (warm) at the start of the run.

## Traffic baseline (`just baseline`)

14 days of ALB `RequestCount` on the live-traffic express gateway
(`app/ecs-express-gateway-alb-9973f5e0/773360e233f7cb84`) — all traffic on that
load balancer, not search alone, so an upper bound on search RPS:

|               | rps                           |
| ------------- | ----------------------------- |
| median minute | 10.53                         |
| p95 minute    | 21.85                         |
| peak minute   | 100.27 (2026-08-29 06:18 UTC) |

Not re-anchored on this peak — per the methodology, the ladder was anchored near
2026-09-09's known cliff (~3rps healthy / ~6rps collapse) and widened upward,
since the ECS change was expected to raise it.

## Capacity ladder (`CACHE_MODE=bust`, steps `1,1.5,2,3,4,6`× a 3rps base)

Auto-aborted during the 4x step (`http_req_failed` crossed the 5% abort
threshold at 19.86%) — the 6x step never ran.

| step | offered rps | document_by_id p95 | documents p95  | labels p95     | passages p95   | http_req_failed |
| ---- | ----------- | ------------------ | -------------- | -------------- | -------------- | --------------- |
| 1x   | ~3          | 810ms              | 960ms          | 960ms          | 859ms          | 0%              |
| 1.5x | ~4.5        | 673ms              | 1.35s          | 1.11s          | 926ms          | 0%              |
| 2x   | ~6          | 892ms              | 2.07s          | 1.87s          | 1.39s          | 0.05%           |
| 3x   | ~9          | 8.66s              | 20.04s         | 28.31s         | 19.57s         | 0.04%           |
| 4x   | ~12         | 29.55s             | 1m0s (timeout) | 1m0s (timeout) | 1m0s (timeout) | 19.86%          |

A `p(95)` of exactly `1m0s` is k6's default request timeout being hit, not a
precise measured value — treat those cells as "at least 60s, or hung", not as
data.

**Reading:** the healthy/collapsed boundary is between 2x (~6rps) and 3x (~9rps)
— not a hard binary cliff the way 2026-09-09 was, but a fast degradation: 3x's
error _rate_ stayed tiny (0.04%, since these are slow responses rather than hard
failures/timeouts), but p95 latency across every route jumped by roughly an
order of magnitude (890ms-2.1s at 2x, to 8.7-28.3s at 3x). 4x is the full
collapse, with all four routes hitting or exceeding k6's 60s timeout and error
rate crossing the abort threshold.

Compared to 2026-09-09 (old config, min=1/max=4: healthy ~3rps, collapsed
~6rps), this run's boundary has moved to roughly **healthy ~6rps, collapsing by
~9rps** — the min=3/max=8 change bought a real increase in safe headroom
(roughly 2x the previous healthy ceiling), but did not remove the underlying
cliff, and the new ceiling is lower than PR #529's sizing arithmetic implied on
its own (that comment sized `max_task_count=8` against a peak of ~22.6rps,
assuming autoscaling reacts in time to reach that many tasks — see below for why
it didn't here).

## Server-side corroboration (`metrics_aws.py`, same window)

| metric             | behaviour                                                                                                                                                                                                                                                                                          |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RunningTaskCount` | Flat at 3 (the new floor) from 10:01 BST through 10:19 BST — i.e. through the entire 3x step and almost all of the 4x collapse. `desired_tasks` only ticked 3→4 at 10:19, and `running` caught up to 4 at 10:20 — by which point ALB p95 was already 27-29s and the run was seconds from aborting. |
| `CpuUtilized`      | Low (~2-24%) through 1x-2x (09:55-10:06), climbing sharply from 10:07 (54%) and pinned at 88-98% from 10:13 (right at the 2x→3x transition) through the rest of the run, reaching 99% (1016/1024) by 10:21.                                                                                        |
| `alb_p95`          | Flat ~0.9-1.4s through 1x-2x, then climbing steeply from 10:07 (1.75s) to 7.1s (10:13), 20-25s (10:14-10:17), and 27.7-29.0s (10:19-10:21) as the 4x step failed.                                                                                                                                  |

**Reading:** this is the same CPU-bound signature as 2026-09-09, just shifted to
a higher offered load. Raising the task-count floor to 3 removed the scale-up
_lag_ for the first burst (no more 1-task cold start), which is why the ceiling
moved up — but once CPU on the existing 3 tasks saturates, the _same_ problem
recurs: target-tracking autoscaling did not add a 4th task until 10:19, by which
point p95 was already in the high-20-second range and the run aborted one minute
later. Raising `max_task_count` to 8 gave more _ceiling_ in principle, but this
run never got anywhere near using it — CPU saturation on 3 tasks, and the
reaction lag to scale beyond that, is still the binding constraint, not the
configured maximum.

Vespa-side metrics were available this run (unlike 2026-09-09) and rule Vespa
out as a contributor: `vespa_cpu` stayed at 2.3-4.8% throughout, including
during the 10:13-10:18 collapse window, and `vespa_p95` stayed flat at 99-208ms
the entire run, with `vespa_memory` static. The bottleneck is entirely within
the search-api ECS task layer, not Vespa.

## Cache-busting check

Not re-verified this run — no changes to the affected route files' cache-busting
logic since 2026-09-09's A/B (108ms p95 uncached vs 8.76s p95 cache-busted), and
the ladder's own healthy-step p95s (810ms-2.07s) are consistent with requests
reaching origin rather than being served from cache.

## Caveats

- Single run at the new config — no repeated-run variance data yet, unlike
  2026-09-09's three same-day runs. Treat the ~6rps/~9rps boundary as
  indicative, not as tightly corroborated as the previous baseline.
- The ladder measures a whole-service cliff (offered load across all four routes
  combined), not each route's individual ceiling in isolation.
- 6x step never ran (aborted at 4x), so the shape of the ladder above ~12rps
  remains unconfirmed.
- `RunningTaskCount` showed 6 running tasks (against a desired of 3) for the
  first ~6 minutes of the metrics window (09:55-10:00 BST), before settling
  to 3. This looks like leftover tasks draining from a prior deploy/scaling
  event rather than anything the ladder itself caused (the k6 run didn't start
  sending load until 08:55:34 UTC / 09:55:34 BST) — not investigated further,
  noted in case it recurs.
- This run's main finding — that autoscaling reacts too slowly to prevent the
  collapse once CPU saturates, regardless of `max_task_count` — suggests
  `min_task_count=3` alone does not fully address the failure mode from
  2026-09-09; a lower `auto_scaling_target_value` (scale out before 70% CPU) or
  a faster-reacting scaling policy (e.g. step scaling on a leading indicator)
  may be needed to actually use the raised `max_task_count=8` ceiling before
  collapse, not just after. Worth raising with whoever owns PR #529 before
  relying on max=8 as real headroom for event traffic.
- Re-run per the "when to re-run" section of the methodology doc, especially
  once the autoscaling policy itself changes (not just min/max task count).

## Threshold changes proposed from this run

`p(95)<2000` in all four affected files: **keep as-is, no change proposed.**
Every measured healthy-step (1x-2x, up to ~6rps) p95 in this run (673ms-2.07s)
sits at or just under the existing 2000ms threshold, and the 3x step's p95s
(8.66s-28.31s) are an order of magnitude past it — the threshold still cleanly
separates "fine" from "degraded" at the current traffic ceiling. The citation
comment in each of the four files should be updated to point at this file
instead of 2026-09-09's, since this run supersedes it as the current baseline
(same config now live, more recent measurement) — this is a comment-only change
(pointing at a new file), not a threshold value change, so it's included here as
a proposal but is lower-stakes than an actual number change.
