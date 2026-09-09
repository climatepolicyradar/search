# pre-launch-perf

Load test for `search-api` ahead of the 2026-09-14 launch: find the RPS at which
it breaks, and turn that into ECS and Vespa provisioning values.

Self-contained on purpose — nothing here imports from `k6/`, and no live code is
modified. `baseline.py` is the one exception: it imports `search.grafana` for
credential resolution only.

```bash
just check                 # prove we can read everything, before burning a window
just baseline              # peak-minute RPS of live search traffic
just dry-run               # 60s harness smoke + guard check
just watch-vespa           # in another terminal, during the run
just run 12                # the real thing, 12 = peak-minute RPS
just aws-metrics 2026-09-08T14:00:00 2026-09-08T14:40:00
```

## What this measures

`load.ts` steps offered load through `1x, 1.5x, 2x, 3x, 5x` of the measured
baseline, 5 minutes per step, across four routes weighted to approximate a
search page view. It uses **`constant-arrival-rate`**, not `ramping-vus`: a
VU-driven test self-throttles, because as latency rises each VU completes fewer
iterations, so offered load silently falls and the breakpoint never appears.

Every scenario is tagged `{step, route}`, so the summary is the deliverable — a
per-step, per-route latency and error table rather than one averaged number.

## Headline result (2026-09-08, 60s dry-run)

**Origin capacity is under ~4 rps on the current config, and the bottleneck is
the API task, not Vespa.**

A 60s run at ~4 offered rps with cache-busting on:

|                                    | value                                                          |
| ---------------------------------- | -------------------------------------------------------------- |
| p95 / median / p99                 | **29.9s** / 15.9s / 60s (timeout)                              |
| `/documents/{id}` median           | **8.4s** — a single key-value GET that takes 25ms as a one-off |
| completed / dropped                | 162 / 75 dropped iterations                                    |
| ALB `TargetResponseTime` p95       | **26.34s** — server-side, so not a client artefact             |
| `RunningTaskCount`                 | **1** (desired 1) — never scaled out                           |
| `CpuUtilized`                      | max **681 of 1024 units (~67%)**                               |
| Vespa `queries.rate`               | **0.02/s**                                                     |
| Vespa `query_latency.95percentile` | **12ms**                                                       |

Two things follow.

**Autoscaling did not fire, exactly as predicted.** CPU peaked at ~67%, just
under the `AVERAGE_CPU` 70% target, while p95 was 26s. Target-tracking on CPU
cannot see this failure, because the task is not CPU-bound — it is blocked and
thrashing. This is the single most important change to make before launch.

**Vespa is not the problem.** It served 12ms p95 at ~1% CPU throughout. Every
second of that 26s was spent in the API task. Do not spend launch budget on
Vespa nodes on this evidence.

The likely mechanism, consistent with the numbers: at 4 rps and 26s latency
there are ~100 requests in flight against a 40-thread anyio pool (one uvicorn
process, all routes sync `def`), and each `/documents` request opens its own
`ThreadPoolExecutor(2 + len(fields))` on top of that. So ~40 in flight each
spawning ~4 more threads, on 1 vCPU, serialising 1.4 MB responses and opening a
fresh TLS connection per Vespa query. CPU never pins because the process is
context-switching, not computing. That points at **more tasks, not more vCPU per
task**, plus reducing per-request fan-out.

## Against live traffic

`baseline.py`, 14 days of the live express ALB at 60s resolution:

|               | rps                           |
| ------------- | ----------------------------- |
| median minute | 11.03                         |
| p95 minute    | 22.58                         |
| peak minute   | 100.27 (2026-08-29 06:18 UTC) |

That is _all_ traffic on that load balancer, not search alone, so it is an upper
bound on search RPS rather than a measurement of it.

Even so: measured origin capacity is **under ~4 rps**, against a median live
minute of 11 and a p95 of 22.6. CloudFront closes some of that gap — but not as
much as this repo's fixtures suggest. The 85-90% hit rate observed above comes
from repeating **five** query terms. Real search traffic has a long tail of
distinct queries, so its hit rate will be materially lower and origin will see a
much larger share than 10-15%. Quantifying that is the one thing that would firm
up the launch verdict: replay a realistic query mix in `CACHE_MODE=realistic`
and measure the actual hit rate. The ~102 real production-shaped terms in
`relevance_tests/` are the obvious corpus for it.

## Next run

**Do not anchor the ladder on the baseline peak.** Now that the ceiling is known
to be single-digit rps, `just run 100` would spend every step far past the cliff
and tell us nothing about where it is. Anchor low and widen:

```bash
just run 1 "1,2,4,8"      # 1, 2, 4, 8 rps -- brackets the observed ~4 rps knee
```

That is the run that produces the actual step -> p95 -> task-count curve. The
60s dry-run above is strongly indicative but it is one minute at one load level,
not a characterised curve.

## Findings from building the harness

All from production, verified rather than inferred.

**0. CloudFront fronts search-api and caches search responses.** This
invalidated an earlier reading of these same dry-runs, so it is worth stating
plainly: a first request Misses, identical repeats Hit, and `age` increments.
The **full query string is in the cache key** (`?_cb=1` and `?_cb=2` both Miss;
repeating `?_cb=1` Hits).

With the 5-term fixture and no cache-busting, the edge absorbed roughly 85-90%
of the load — the ALB saw ~40 requests out of 301 offered — and the run showed a
flattering p95 of 46ms that was mostly CloudFront, not the API. That is why
`load.ts` defaults to `CACHE_MODE=bust`. **A `realistic` run measures what users
experience; only a `bust` run measures what the origin must survive.**

**1. `/search/documents` returns 785 KB — 1.4 MB per request.** At
`page_size=10`. Measured:

| route                             | bytes     |
| --------------------------------- | --------- |
| `/documents?query=…`              | 785,599   |
| `/documents?query=…&fields=` both | 1,401,065 |
| `/passages?query=…`               | 19,652    |
| `/labels?query=…`                 | 2,632     |
| `/documents/{id}`                 | 7,000     |

That is the unconditional aggregations grouping (`max(5000)` over two grouping
fields, `api/routers.py:109-113`) being serialised into every response whether
the caller wants it or not, then doubled by `fields=`.

Two consequences. It is a product/cost problem — every search page view pulls ~1
MB of facet JSON. And it **caps what can be tested from a laptop**: at 45% of
traffic on `/documents`, 2x of a 12 rps baseline is already ~15 MB/s (~120 Mbps)
sustained, and 5x is ~300 Mbps. Past roughly 2x we would be measuring home
broadband, not the API. Either run the high steps from EC2 in `eu-west-1`, or
treat >2x results as invalid.

**2. `min_task_count=1` means there is no redundancy and no warm spare.**
Confirmed live: `RunningTaskCount` and `DesiredTaskCount` are both 1. Any deploy
or task recycle takes capacity to zero, and there is nothing to absorb a spike
while a second task starts. Raise it to at least 2 regardless of what throughput
testing concludes.

**3. Vespa's search-handler pool is 20 threads per container node.** From
`/state/v1/metrics`: `search-handler` has `size: 20`, `max_allowed_size: 20`,
`work_queue.capacity: 800`. Two container nodes, so **40 concurrent searches
cluster-wide**, then an 800-deep queue, then rejection. That is a hard, knowable
Vespa ceiling — and because `/documents` issues 2–8 Vespa queries per HTTP
request, 40 concurrent searches is reached at far fewer than 40 concurrent HTTP
requests.

**4. A feed runs at ~512 UPDATE ops/sec outside the documented cron windows.**
Sustained across samples at 15:18 UTC
(`feed.operations{operation:UPDATE,api:documentV1}`, ~512/s, 388 open
connections on the feed port); documented crons are 03:00–05:00 UTC. Decision
taken: leave it running and treat it as representative ambient load. It is not
distorting results — Vespa sat at ~1% CPU and 12ms p95 throughout, so the feed
has ample headroom and is not competing with query traffic.

**5. `/Grafana/*` SSM parameters do not exist in the production account.**
`search/config.py:136` and `search/grafana.py` reference
`/Grafana/MetricUserApiToken`, `/Grafana/MetricQueryURL` and
`/Grafana/MetricUserId`; all three return `ParameterNotFound` (only
`/OTel/Collector/*` exists). So `baseline.py` cannot resolve live-traffic
metrics that way, and anything else depending on `GrafanaSession` is silently
broken too. Baseline has to come from CloudWatch instead.

**6. The search-api ALB is
`app/ecs-express-gateway-alb-b0a18abd/460db4bc905aacb6`.** Identified
empirically — the AWS-managed Express Gateway ALBs carry only an
`AmazonECSManaged` tag, no cluster or service tag, so `metrics_aws.py`'s
tag-matching cannot find them and `--load-balancer` must be passed explicitly.
The other express ALB (`9973f5e0`) carries ~5-7 rps of live traffic and is not
this service.

## Metric coverage, and its limits

Verified, not assumed:

- **`/state/v1/metrics` with `VESPA_READ_TOKEN` works** and returns ~229
  container-node metrics: `jdisc.thread_pool.*`, `query_latency`,
  `serverNumRequests`, `serverNumOpenConnections`, `mem.*`, `jvm.*`.
- **It does not return `content.proton.*`.** Those live on content nodes, which
  the data plane will not route to. Content-node CPU, memory and disk only come
  from the `vespa` CloudWatch namespace at **5-minute** resolution, i.e. roughly
  one datapoint per load step. Coarse, but it is all we have.
- **`/metrics/v2/values` returns node roles with empty `services` arrays** — no
  values. Used only to record topology (confirms 2 container + 2 content + 3
  cluster-controller + 1 logserver).
- Each poll is load-balanced to _one_ of the two container nodes, so treat
  thread-pool numbers as a sampled distribution, not one node's timeline.
- **`ENV` is never set on the prod ECS service** (`infra/__main__.py:616-620`),
  so the API's own OTel metrics go to the _staging_ collector tagged
  `environment=development`. Don't use them here; use ALB `TargetResponseTime`
  for server-side latency.

## Reading the break

| Symptom                                             | Bottleneck                                                         |
| --------------------------------------------------- | ------------------------------------------------------------------ |
| `RunningTaskCount` stuck at 1 while p95 climbs      | autoscaling metric never fired — the predicted failure             |
| p95 high, `CpuUtilized` low, tasks maxed            | anyio 40-thread ceiling (1 uvicorn process, all routes sync `def`) |
| Vespa `search-handler` `work_queue.size` rising     | 40-concurrent-search cluster ceiling                               |
| Vespa `query_latency` tracks API p95                | content nodes — slow to change, decide early                       |
| `TargetConnectionErrorCount` / sudden 5xx           | port exhaustion from unpooled per-query Vespa connections          |
| `http_req_connecting` / `tls_handshaking` inflating | **the laptop**, not the API — see finding 1                        |

`dropped_iterations` with no matching server errors means `maxVUs` was too low
and the run under-delivered load; raise it and re-run.

## Prerequisites

- `aws login` (profile `production`) — needed by `baseline.py` and
  `metrics_aws.py`. Not needed for `load.ts` or `metrics_vespa.py`.
- `VESPA_ENDPOINT` / `VESPA_READ_TOKEN` — already in the repo-root `.env`,
  loaded automatically by this directory's `justfile`.
- `npm install` once, for the k6 type-check.
