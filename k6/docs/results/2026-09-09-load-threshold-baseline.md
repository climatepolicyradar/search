# Load threshold baseline — 2026-09-09

Results of applying [the methodology](../load-threshold-methodology.md) ahead of
the 2026-09-14 search launch. Referenced by the `load` profile thresholds in
`k6/routes/documents/fields-combinations.ts`,
`k6/routes/documents/{document_id}/index.ts`, `k6/routes/passages/index.ts`, and
`k6/routes/passages/filter-combinations.ts`.

Run against production (`api.climatepolicyradar.org/search`) using
`pre-launch-perf/` from PR
[climatepolicyradar/search#525](https://github.com/climatepolicyradar/search/pull/525).

## Traffic baseline (`just baseline`)

14 days of ALB `RequestCount` on the live-traffic express gateway
(`app/ecs-express-gateway-alb-9973f5e0/773360e233f7cb84`) — all traffic on that
load balancer, not search alone, so an upper bound on search RPS:

|               | rps    |
| ------------- | ------ |
| median minute | 10.87  |
| p95 minute    | 22.30  |
| peak minute   | 100.27 |

## Capacity ladder (`CACHE_MODE=bust`, steps `1,2,4,8`× a 1rps base)

Auto-aborted during the 4x step (`http_req_failed` crossed the 5% abort
threshold at 19.82%) — the 8x step never ran.

| step | offered rps | document_by_id p95 | documents p95  | labels p95     | passages p95   | http_req_failed |
| ---- | ----------- | ------------------ | -------------- | -------------- | -------------- | --------------- |
| 1x   | ~1.5        | 1.20s              | 1.16s          | 1.08s          | 1.12s          | 0%              |
| 2x   | ~3          | 998ms              | 1.51s          | 1.66s          | 1.51s          | 0%              |
| 4x   | ~6          | 26.15s             | 1m0s (timeout) | 1m0s (timeout) | 1m0s (timeout) | 19.82%          |

A `p(95)` of exactly `1m0s` is k6's default request timeout being hit, not a
precise measured value — treat those cells as "at least 60s, or hung", not as
data. `document_by_id`'s cheap key-value lookup was the one route that mostly
completed within the timeout at 4x, giving the one real number in that row.

**Reading:** a hard cliff between 2x (~3rps, healthy) and 4x (~6rps, collapsed)
— not a gradual degradation. The healthy region tops out with p95 in the
998ms–1.66s range across routes.

## Server-side corroboration (`metrics_aws.py`, same window)

| metric             | behaviour                                                                                           |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| `RunningTaskCount` | 1 → 2 around the 4x spike — autoscaling did fire                                                    |
| `CpuUtilized`      | spiked to ~109% at the start of the spike, then dropped to ~2.7% for the rest of the failing window |
| `alb_p95`          | recovering to 0.20s–1.07s once the run aborted and load dropped                                     |

**Reading:** CPU was _not_ pinned during the failure — it dropped to near idle
while requests were still timing out and erroring. That rules out a simple
CPU/autoscaling-target explanation and points at saturation elsewhere (thread
pool / connection pool), consistent with PR #525's own finding from its initial
dry-run. This means the ~3–6rps ceiling is not purely a "scale up ECS" problem —
raising task count alone would not be expected to move this number by itself.

## Cache-busting cross-check (10 VUs, `documents` route, `fields-combinations.ts`'s worst-case request shape)

Run as an ad-hoc probe (not committed) to check whether the `k6/routes/**`
`load` profiles — which do **not** cache-bust and cycle through only 1–5
distinct query/filter/ID values — were measuring origin or CloudFront:

|                      | offered rps | p95   |
| -------------------- | ----------- | ----- |
| without cache-buster | 8.58        | 108ms |
| with cache-buster    | 1.23        | 8.76s |

**Reading:** confirms the `k6/routes/**` `load` profiles were almost certainly
measuring CloudFront, not origin, prior to this fix — an ~80x difference in p95
for the identical request shape at the identical VU count, differing only in
whether the cache was bypassed. Cache-busting was added to all four affected
`load` profiles as a result (see git history for
`k6/routes/documents/fields-combinations.ts`,
`k6/routes/documents/{document_id}/index.ts`, `k6/routes/passages/index.ts`,
`k6/routes/passages/filter-combinations.ts` around 2026-09-09).

## Caveats

- Single run — no repeated-run variance data yet, so treat exact figures as
  indicative of the right order of magnitude, not a tightly fitted number.
- The ladder measured a whole-service cliff (offered load across all four routes
  combined), not each route's individual ceiling in isolation.
- 8x step never ran (aborted at 4x), so the shape of the ladder above the cliff
  is unconfirmed.
- Re-run per the "when to re-run" section of the methodology doc, especially
  once any fix targeting the thread-pool/connection-pool bottleneck lands — this
  baseline reflects a known-suboptimal configuration, not a post-fix ceiling.
