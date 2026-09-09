"""
Peak-minute RPS of live traffic, to anchor the load test's steps.

Reads CloudWatch only -- nothing in this folder ever sends traffic to the old
stack.

Originally written against the Grafana span metrics that search/grafana.py
uses, which would have isolated `POST /api/v1/searches` exactly. That path is
dead: /Grafana/MetricUserApiToken, /Grafana/MetricQueryURL and
/Grafana/MetricUserId all return ParameterNotFound in the production account
(only /OTel/Collector/* exists). See README finding 5.

So this uses ALB RequestCount at 60s resolution instead. Important caveat:
**that counts all traffic to the load balancer, not just search**, so it is an
upper bound on search RPS, not a measurement of it. Stated in the output rather
than hidden, because using it as if it were search-only would over-size the
test.

Reports peak / p95 / median minute. Use the **peak** as BASELINE_RPS.

Usage:
    python baseline.py                    # live traffic ALB, last 14 days
    python baseline.py --load-balancer app/... --days 30
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import statistics
import sys
from typing import Final

import boto3

logging.basicConfig(
    format="%(asctime)s\t%(levelname)s\t%(message)s", level=logging.INFO
)
logger = logging.getLogger("baseline")

REGION: Final = "eu-west-1"

# The express-gateway ALB carrying live traffic. Not search-api's -- that one
# is nearly idle (see README finding 6). Both carry only an `AmazonECSManaged`
# tag, so neither is discoverable by tag; these were identified by observing
# which saw dry-run traffic.
LIVE_TRAFFIC_ALB: Final = "app/ecs-express-gateway-alb-9973f5e0/773360e233f7cb84"

# CloudWatch caps a single GetMetricStatistics response at 1440 datapoints, so
# 60s resolution covers 24h per call. Longer ranges are paged day by day.
MAX_POINTS_PER_CALL: Final = 1440


class BaselineError(RuntimeError):
    """
    No usable traffic data. Raised rather than defaulting to a number.

    A wrong baseline silently distorts every step of the load test, so an
    invented default is worse than no answer at all.
    """


def request_counts(
    session: boto3.Session,
    load_balancer: str,
    start: dt.datetime,
    end: dt.datetime,
    period_s: int,
) -> list[tuple[dt.datetime, float]]:
    """Per-period request counts, paged so long ranges keep 60s resolution."""
    cloudwatch = session.client("cloudwatch", region_name=REGION)
    window = dt.timedelta(seconds=period_s * MAX_POINTS_PER_CALL)

    points: list[tuple[dt.datetime, float]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + window, end)
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/ApplicationELB",
            MetricName="RequestCount",
            Dimensions=[{"Name": "LoadBalancer", "Value": load_balancer}],
            StartTime=cursor,
            EndTime=chunk_end,
            Period=period_s,
            Statistics=["Sum"],
        )
        points.extend(
            (point["Timestamp"], point["Sum"]) for point in response["Datapoints"]
        )
        cursor = chunk_end

    if not points:
        raise BaselineError(
            f"No RequestCount datapoints for {load_balancer} between {start} "
            f"and {end}. Check the ALB dimension and that the profile can read "
            f"{REGION}."
        )

    points.sort(key=lambda pair: pair[0])
    return points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--period", type=int, default=60, help="seconds; 60 = per-minute")
    parser.add_argument("--load-balancer", default=LIVE_TRAFFIC_ALB)
    parser.add_argument("--profile", default="production")
    args = parser.parse_args()

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=args.days)

    session = boto3.Session(profile_name=args.profile)
    points = request_counts(
        session, args.load_balancer, start, end, args.period
    )

    # Sum over the period -> requests per second.
    rps = sorted(count / args.period for _, count in points)
    peak = rps[-1]
    p95 = statistics.quantiles(rps, n=100)[94] if len(rps) > 1 else peak
    median = statistics.median(rps)

    peak_at = max(points, key=lambda pair: pair[1])[0]

    logger.info(f"--- {args.load_balancer} over the last {args.days} days ---")
    logger.info(f"datapoints    : {len(rps)} at {args.period}s resolution")
    logger.info(f"median minute : {median:.2f} rps")
    logger.info(f"p95 minute    : {p95:.2f} rps")
    logger.info(f"PEAK minute   : {peak:.2f} rps  (at {peak_at:%Y-%m-%d %H:%M} UTC)")
    logger.info("")
    logger.info(
        "CAVEAT: ALB RequestCount is ALL traffic to this load balancer, not "
        "just search. Treat this as an upper bound on search RPS."
    )
    logger.info(
        "Do NOT feed the peak straight into `just run`. Measured origin "
        "capacity is single-digit rps (see README), so a ladder anchored on "
        f"{peak:.0f} would spend every step past the cliff. Anchor low and "
        "widen the multipliers, e.g. `just run 1 '1,2,4,8'`."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
