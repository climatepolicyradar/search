# Breakpoint test baseline — 2026-09-09

Results of applying [the methodology](../load-threshold-methodology.md).
Referenced by the `load` profile thresholds in
`k6/tests/smoke-load/routes/documents/fields-combinations.ts`,
`k6/tests/smoke-load/routes/documents/{document_id}/index.ts`,
`k6/tests/smoke-load/routes/passages/index.ts`, and
`k6/tests/smoke-load/routes/passages/filter-combinations.ts`.

Run against production (`api.climatepolicyradar.org/search`) using
`k6/tests/breakpoint/`, on the
`feature/fus-403-provision-k6-load-tests-via-pulumi-scheduled-in-grafana` branch
(post-rebase onto `main`, with cache-busting already applied to the four route
files above).

## Traffic baseline

Not re-measured this run — anchored directly on the known cliff from prior runs
the same day (healthy ~3rps, collapse ~6rps). See git history for
`just baseline` output if the live-traffic figures are needed; not reproduced
here since they weren't re-pulled.

## Capacity ladder (`CACHE_MODE=bust`, steps `1,2,4,8`× a 1rps base)

Auto-aborted during the 4x step (`http_req_failed` crossed the 5% abort
threshold at 20.94%) — the 8x step never ran. Third same-day run with this
shape; all three agree closely on where the cliff is.

| step | offered rps | document_by_id p95 | documents p95  | labels p95     | passages p95   | http_req_failed |
| ---- | ----------- | ------------------ | -------------- | -------------- | -------------- | --------------- |
| 1x   | ~1.5        | 977ms              | 1.12s          | 1.14s          | 957ms          | 0%              |
| 2x   | ~3          | 960ms              | 1.85s          | 1.4s           | 1.77s          | 0%              |
| 4x   | ~6          | 26.76s             | 1m0s (timeout) | 1m0s (timeout) | 1m0s (timeout) | 20.94%          |

A `p(95)` of exactly `1m0s` is k6's default request timeout being hit, not a
precise measured value — treat those cells as "at least 60s, or hung", not as
data.

**Reading:** the same hard cliff as the two earlier same-day runs, between 2x
(~3rps, healthy) and 4x (~6rps, collapsed) — not a gradual degradation.
Healthy-region p95 across all three runs so far has ranged roughly 860ms–1.85s
depending on route and run; use that range, not a single point figure, when
setting a threshold.

## Server-side corroboration (`metrics_aws.py`, same window)

| metric             | behaviour                                                                                                                                               |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RunningTaskCount` | 1 → 2 at 16:55 BST, i.e. _after_ the run had already aborted (16:53:55) — autoscaling did not act in time to help this run                              |
| `CpuUtilized`      | climbed from ~180/1024 (1x) to ~700-750/1024 (~70-73%) through the 2x step, then pinned at 987-1002/1024 (~96-98%) during the 4x collapse (16:52-16:53) |
| `alb_p95`          | rising through the run: ~1-2s during 1x/2x, up to 29.31s by 16:53 as the 4x step failed                                                                 |

**Reading:** this is the third same-day run, and the third to show CPU climbing
into saturation through the 2x step and pinning near 100% exactly at the 4x
collapse — this is now the consistent, reproducible signature, not an outlier.
(An earlier run today showed CPU dropping to near-idle during a comparable
failure, and PR #525's original dry-run found the same — those look like they
were the outliers relative to this pattern, not the other way round; worth
another look if it recurs, but three consistent CPU-bound runs versus one
near-idle one is enough to act on for now.) Combined with `RunningTaskCount`
only reaching 2 a full 1-2 minutes _after_ the run had already aborted,
target-tracking on CPU is not reacting fast enough to prevent the collapse — by
the time autoscaling would help, the ladder has already moved past the failing
step. This is a CPU-bound capacity ceiling at the current task sizing, not
primarily a thread-pool/connection-pool issue as earlier analysis (based on the
one near-idle-CPU run) suggested.

## Cache-busting check

Verified in place: this branch's `k6/tests/smoke-load/routes/**` load profiles
now cache-bust (commit `7f5867d`, reapplying the fix from the original `a8aeb00`
that was reverted on a different branch). Not independently re-A/B'd this run,
since the fix was verified directly against production earlier the same day
(108ms p95 uncached vs 8.76s p95 cache-busted, same shape/VU count) and the code
hasn't changed since.

## Caveats

- Third run of the day with this exact ladder shape — cliff location is now
  well-corroborated (3/3 runs agree on ~3rps healthy / ~6rps collapse), but the
  CPU-bound reading is only 3/4 total runs today (one showed near-idle CPU,
  matching PR #525's original dry-run) — worth another look if a future run
  disagrees again.
- The ladder measures a whole-service cliff (offered load across all four routes
  combined), not each route's individual ceiling in isolation.
- 8x step never ran (aborted at 4x) in any run today, so the shape of the ladder
  above the cliff remains unconfirmed.
- Vespa metrics via `metrics_vespa.py` were not available this run (no
  `VESPA_ENDPOINT`/`VESPA_READ_TOKEN` in the repo-root `.env`), so whether Vespa
  itself is contributing to the CPU-bound signature (vs. purely the API task) is
  not resolved by this data.
- Re-run per the "when to re-run" section of the methodology doc, especially
  once `min_task_count` or CPU allocation changes — this baseline reflects the
  current (1-task-minimum, CPU-saturating) configuration.

## Threshold changes applied from this run

`p(95)<2000` in all four affected files is being **kept at `2000`**. It sits
above every measured healthy-step p95 across all three same-day runs
(860ms–1.85s) with real headroom for run-to-run variance, and well below the
collapse values (26s+/timeout at 4x) — it continues to separate "fine" from
"broken" correctly, and three runs' worth of variance data suggests the healthy
region moves around enough (860ms to 1.85s, over 2x) that a much tighter
threshold risks flapping on noise rather than catching a real regression. The
citation comment in each of the four files is updated to point at this file
instead of the deferred Fusion monitoring RFC line.
