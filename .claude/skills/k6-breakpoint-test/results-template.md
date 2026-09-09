# Load threshold baseline — {{DATE}}

Results of applying [the methodology](../load-threshold-methodology.md).
Referenced by the `load` profile thresholds in {{LIST_OF_AFFECTED_ROUTE_FILES}}.

Run against production (`api.climatepolicyradar.org/search`) using
`k6/tests/breakpoint/` (originally landed as `pre-launch-perf/` in
[climatepolicyradar/search#525](https://github.com/climatepolicyradar/search/pull/525),
moved under `k6/` afterwards — check it hasn't moved again since).

## Traffic baseline (`just baseline`)

{{DAYS}} days of ALB `RequestCount` on the live-traffic express gateway
(`{{LOAD_BALANCER}}`) — all traffic on that load balancer, not search alone, so
an upper bound on search RPS:

|               | rps                        |
| ------------- | -------------------------- |
| median minute | {{MEDIAN_RPS}}             |
| p95 minute    | {{P95_RPS}}                |
| peak minute   | {{PEAK_RPS}} ({{PEAK_AT}}) |

## Capacity ladder (`CACHE_MODE=bust`, steps `{{STEPS}}`× a {{BASELINE_RPS}}rps base)

{{ABORT_OR_COMPLETION_NOTE — e.g. "Auto-aborted during the Nx step
(http_req_failed crossed the 5% abort threshold at X%) — later steps never
ran." or "Completed all steps without aborting."}}

| step     | offered rps | {{ROUTE_1}} p95 | {{ROUTE_2}} p95 | {{ROUTE_3}} p95 | {{ROUTE_4}} p95 | http_req_failed |
| -------- | ----------- | --------------- | --------------- | --------------- | --------------- | --------------- |
| {{STEP}} | {{RPS}}     | {{P95}}         | {{P95}}         | {{P95}}         | {{P95}}         | {{ERROR_RATE}}  |

A `p(95)` of exactly `1m0s` is k6's default request timeout being hit, not a
precise measured value — treat those cells as "at least 60s, or hung", not as
data.

**Reading:** {{DESCRIBE WHERE THE BOUNDARY BETWEEN HEALTHY AND COLLAPSED
STEPS FALLS, AND WHETHER IT'S A GRADUAL DEGRADATION OR A HARD CLIFF}}

## Server-side corroboration (`metrics_aws.py`, same window)

| metric             | behaviour                                                       |
| ------------------ | --------------------------------------------------------------- |
| `RunningTaskCount` | {{DID AUTOSCALING FIRE, AND WHEN RELATIVE TO THE FAILING STEP}} |
| `CpuUtilized`      | {{WAS CPU PINNED DURING THE FAILURE, OR LOW/DROPPING}}          |
| `alb_p95`          | {{SERVER-SIDE LATENCY TREND}}                                   |

**Reading:** {{STATE WHETHER THE BOTTLENECK LOOKS CPU-BOUND (AUTOSCALING
SHOULD HELP) OR SOMETHING ELSE — THREAD POOL, CONNECTION POOL, VESPA — AND
WHAT THAT IMPLIES FOR WHETHER RAISING TASK COUNT ALONE WOULD FIX IT}}

## Cache-busting check

{{IF THIS RUN VERIFIED CACHE-BUSTING IS STILL IN PLACE ON THE TARGET
ROUTES' load PROFILES, SAY SO BRIEFLY AND SKIP THE FULL A/B. IF A NEW ROUTE
WAS ADDED SINCE THE LAST RUN AND HASN'T BEEN CHECKED, DO THE A/B (SAME
SHAPE, SAME VU/RATE, WITH AND WITHOUT THE _cb PARAM) AND RECORD IT HERE.}}

## Caveats

- Single run — no repeated-run variance data yet unless otherwise noted, so
  treat exact figures as indicative of the right order of magnitude, not a
  tightly fitted number.
- The ladder measures a whole-service cliff (offered load across all routes
  combined), not each route's individual ceiling in isolation, unless run
  per-route in isolation.
- {{NOTE ANY STEPS THAT DIDN'T RUN, OR OTHER GAPS}}
- Re-run per the "when to re-run" section of the methodology doc.

## Threshold changes proposed from this run

{{FOR EACH k6/routes/** load PROFILE THIS RUN INFORMS: STATE WHETHER THE
EXISTING p(95)<Nms VALUE STILL SITS ABOVE THE MEASURED HEALTHY CEILING AND
BELOW THE COLLAPSE POINT. IF NOT, PROPOSE A NEW VALUE AND SAY WHY. DO NOT
EDIT THE ROUTE FILES YOURSELF — THIS SECTION IS THE PROPOSAL FOR THE USER
TO CONFIRM.}}
