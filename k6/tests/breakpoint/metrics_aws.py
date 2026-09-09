"""
Pull the ECS and ALB metric window for a load-test run.

Run this *after* a k6 run, passing the run's start and end times. CloudWatch
lags by a minute or two, so leave a short gap before pulling.

Covers what the direct Vespa scrape cannot:
- ECS task count and per-task CPU/memory, i.e. whether autoscaling fired.
- ALB server-side latency and error counts, which are the honest view of what
  users would have seen -- k6's numbers include the laptop's own network.
- Vespa content-node metrics, only available via the `vespa` CloudWatch
  namespace at 5-minute resolution (the metrics_infra Lambda's emit rate), so
  expect ~1 datapoint per load step. Coarse, but it is the only content-node
  view we have.

The search-api ALB is created and owned by AWS for the ECS Express Gateway
service, so it is not an addressable Pulumi resource and its ARN has to be
discovered at runtime by matching the target group to the service.

Usage:
    python metrics_aws.py --start 2026-09-08T14:00:00 --end 2026-09-08T14:40:00
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import sys
from typing import Any, Final

import boto3

logging.basicConfig(
    format="%(asctime)s\t%(levelname)s\t%(message)s", level=logging.INFO
)
logger = logging.getLogger("metrics_aws")

REGION: Final = "eu-west-1"
CLUSTER: Final = "search"
SERVICE: Final = "search-api"
VESPA_APPLICATION_ID: Final = "climate-policy-radar.search.search-production"
PERIOD_S: Final = 60


class AwsMetricsError(RuntimeError):
    """
    A metric pull failed or returned nothing identifiable.

    Raised rather than returning empty series: an empty list here is
    indistinguishable from "the service was genuinely idle", which would turn a
    broken credential into a confident, wrong conclusion about capacity.
    """


def find_load_balancer(session: boto3.Session) -> str:
    """
    Return the ALB name CloudWatch knows the search-api ALB by.

    The AWS-managed Express Gateway ALB is tagged with the cluster/service it
    fronts. We match on that rather than on a name pattern, because the name is
    AWS's to choose and may change.
    """
    elbv2 = session.client("elbv2", region_name=REGION)
    candidates: list[tuple[str, str]] = []
    paginator = elbv2.get_paginator("describe_load_balancers")
    for page in paginator.paginate():
        for lb in page["LoadBalancers"]:
            arn = lb["LoadBalancerArn"]
            # CloudWatch's LoadBalancer dimension is the trailing
            # "app/<name>/<id>" portion of the ARN, not the ARN itself.
            dimension = arn.split(":loadbalancer/")[-1]
            candidates.append((arn, dimension))

    if not candidates:
        raise AwsMetricsError(
            f"no load balancers found in {REGION}; check credentials and region"
        )

    for arn, dimension in candidates:
        tags = elbv2.describe_tags(ResourceArns=[arn])["TagDescriptions"][0]["Tags"]
        flat = {tag["Key"]: tag["Value"] for tag in tags}
        if CLUSTER in flat.values() or SERVICE in flat.values():
            logger.info(f"matched ALB by tag: {dimension}")
            return dimension

    raise AwsMetricsError(
        f"could not identify the {SERVICE} ALB by tag among "
        f"{[d for _, d in candidates]}. Pass --load-balancer to override."
    )


def _query(
    name: str,
    namespace: str,
    metric: str,
    dimensions: dict[str, str],
    stat: str,
) -> dict[str, Any]:
    return {
        "Id": name,
        "MetricStat": {
            "Metric": {
                "Namespace": namespace,
                "MetricName": metric,
                "Dimensions": [
                    {"Name": k, "Value": v} for k, v in dimensions.items()
                ],
            },
            "Period": PERIOD_S,
            "Stat": stat,
        },
        "ReturnData": True,
    }


def build_queries(load_balancer: str) -> list[dict[str, Any]]:
    ecs_dims = {"ClusterName": CLUSTER, "ServiceName": SERVICE}
    alb_dims = {"LoadBalancer": load_balancer}
    vespa_dims = {"applicationId": VESPA_APPLICATION_ID}

    return [
        # Did autoscaling fire? This is the headline question.
        _query("ecs_running_tasks", "ECS/ContainerInsights", "RunningTaskCount", ecs_dims, "Average"),
        _query("ecs_desired_tasks", "ECS/ContainerInsights", "DesiredTaskCount", ecs_dims, "Average"),
        _query("ecs_cpu", "ECS/ContainerInsights", "CpuUtilized", ecs_dims, "Average"),
        _query("ecs_memory", "ECS/ContainerInsights", "MemoryUtilized", ecs_dims, "Average"),
        # Server-side truth, excluding the laptop's network.
        _query("alb_p95", "AWS/ApplicationELB", "TargetResponseTime", alb_dims, "p95"),
        _query("alb_p99", "AWS/ApplicationELB", "TargetResponseTime", alb_dims, "p99"),
        _query("alb_requests", "AWS/ApplicationELB", "RequestCount", alb_dims, "Sum"),
        _query("alb_5xx", "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", alb_dims, "Sum"),
        # Connection errors are the signature of ephemeral-port exhaustion from
        # the API's unpooled per-query Vespa connections.
        _query("alb_conn_errors", "AWS/ApplicationELB", "TargetConnectionErrorCount", alb_dims, "Sum"),
        _query("alb_rejected", "AWS/ApplicationELB", "RejectedConnectionCount", alb_dims, "Sum"),
        # Vespa, incl. the content-node metrics the direct scrape cannot reach.
        # 5-minute emit rate, so roughly one point per load step.
        _query("vespa_queries", "vespa", "queries.rate", vespa_dims, "Average"),
        _query("vespa_p95", "vespa", "query_latency.95percentile", vespa_dims, "Average"),
        _query("vespa_cpu", "vespa", "cpu", vespa_dims, "Average"),
        _query("vespa_memory", "vespa", "content.proton.resource_usage.memory.average", vespa_dims, "Average"),
        _query("vespa_5xx", "vespa", "http.status.5xx", vespa_dims, "Average"),
    ]


def fetch(
    session: boto3.Session, start: dt.datetime, end: dt.datetime, load_balancer: str
) -> dict[str, Any]:
    cloudwatch = session.client("cloudwatch", region_name=REGION)
    queries = build_queries(load_balancer)

    response = cloudwatch.get_metric_data(
        MetricDataQueries=queries,
        StartTime=start,
        EndTime=end,
        ScanBy="TimestampAscending",
    )

    series: dict[str, Any] = {}
    for result in response["MetricDataResults"]:
        series[result["Id"]] = {
            "timestamps": [ts.isoformat() for ts in result["Timestamps"]],
            "values": result["Values"],
            "status": result.get("StatusCode"),
        }

    populated = [name for name, data in series.items() if data["values"]]
    if not populated:
        raise AwsMetricsError(
            "every metric came back empty. Either the window is wrong, "
            "CloudWatch has not caught up yet (wait ~2 min after the run), "
            f"or the credentials cannot read {REGION}. Window was {start} to {end}."
        )

    empty = sorted(set(series) - set(populated))
    if empty:
        # Not fatal: Container Insights and the 5-min Vespa emitter genuinely
        # may have no point in a short window, and some ALB metrics only exist
        # once non-zero. Say so rather than letting a silent gap read as zero.
        logger.warning(f"no datapoints for: {', '.join(empty)}")

    return series


def summarise(series: dict[str, Any]) -> None:
    logger.info("--- summary ---")
    for name, data in sorted(series.items()):
        values = data["values"]
        if not values:
            logger.info(f"{name:20s} (no data)")
            continue
        logger.info(
            f"{name:20s} n={len(values):3d} "
            f"min={min(values):10.2f} max={max(values):10.2f} "
            f"mean={sum(values) / len(values):10.2f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="UTC ISO8601, e.g. 2026-09-08T14:00:00")
    parser.add_argument("--end", required=True, help="UTC ISO8601")
    parser.add_argument("--out", default="results/aws.json")
    parser.add_argument("--profile", default="production")
    parser.add_argument(
        "--load-balancer",
        default=None,
        help="CloudWatch LoadBalancer dimension (app/<name>/<id>); "
        "discovered by tag if omitted",
    )
    args = parser.parse_args()

    start = dt.datetime.fromisoformat(args.start).replace(tzinfo=dt.timezone.utc)
    end = dt.datetime.fromisoformat(args.end).replace(tzinfo=dt.timezone.utc)
    if end <= start:
        raise AwsMetricsError(f"--end ({end}) must be after --start ({start})")

    session = boto3.Session(profile_name=args.profile)
    load_balancer = args.load_balancer or find_load_balancer(session)

    series = fetch(session, start, end, load_balancer)
    summarise(series)

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "load_balancer": load_balancer,
                "series": series,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
