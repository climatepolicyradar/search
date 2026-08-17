"""
Prefect deployment for the vespa-feeder flows.

Run with: uv run python vespa-feeder/deployments.py
"""

import os

import boto3
from export_production_snapshot import export_production_snapshot
from feed_from_production import feed_from_production
from prefect.docker import DockerImage
from prefect.variables import Variable

_WORK_POOL = "mvp-prod-ecs"


_DEFAULT_JOB_VARIABLES_NAME = "ecs-default-job-variables-prefect-mvp-prod"

# The work pool's defaults (cpu=256, memory=512) are sized for small
# orchestration tasks; a full feed is hours of download + `vespa feed`, so it
# gets the same cpu/memory as vespa-feeder/deployments.py's passages feed.
# That one A/B tested cpu=2048 against 1024 and found no measurable
# difference, so the constraint is Vespa's server-side feed capacity rather
# than local CPU - no reason to go above 1024 here either.
#
# Deliberately no ephemeralStorage override: feed_from_production.py streams
# the snapshot one shard at a time (download -> feed -> delete), so it needs
# ~200MB of disk regardless of corpus size, and Fargate's default 20GiB is
# ample. If that flow ever goes back to downloading the whole snapshot up
# front, this needs to grow to the full corpus size instead - ~75GiB as of
# 2026-08-11, and climbing.
_FEED_JOB_VARIABLES = {
    "cpu": 1024,
    "memory": 4096,
}

if __name__ == "__main__":
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name or os.environ.get("AWS_REGION")
    if not region:
        raise RuntimeError(
            "No AWS region configured - set AWS_REGION/AWS_DEFAULT_REGION or a profile "
            "region. Without it the ECR image URI becomes '...ecr.None.amazonaws.com' "
            "and ECS can't pull the image."
        )
    image_name = f"{account_id}.dkr.ecr.{region}.amazonaws.com/search-vespa-dev"

    default_job_variables = Variable.get(_DEFAULT_JOB_VARIABLES_NAME)
    if not isinstance(default_job_variables, dict):
        raise ValueError(
            f"Variable {_DEFAULT_JOB_VARIABLES_NAME} not found or is not a dict in Prefect"
        )

    # Unlike ../vespa-feeder/deployments.py, this is not scheduled - there's no
    # single shared target instance to feed. Each engineer's dev instance is
    # created/fed ad hoc (see justfile), so this deployment only exists to be
    # triggered manually with an explicit instance, e.g.:
    #   prefect deployment run 'search-vespa-dev-feed-from-production/search-vespa-dev-feed-from-production' \
    #       -p target=climate-policy-radar.search-dev.<instance> \
    #       -p sample_percent=100
    feed_from_production.deploy(
        "search-vespa-dev-feed-from-production",
        work_pool_name=_WORK_POOL,
        image=DockerImage(
            name=image_name,
            tag="latest",
        ),
        job_variables={**default_job_variables, **_FEED_JOB_VARIABLES},
        parameters={
            "sample_percent": 100,  # override with -p sample_percent=... per run
        },
        description="Feed from production to a local Vespa dev instance (run manually with -p instance=...)",
        build=False,
        push=False,
    )
    print("Deployed search-vespa-dev-feed-from-production")

    # Scheduled daily - see export_production_snapshot.py's module docstring
    # for why this exists (feed_from_production.py's `vespa visit` is slow
    # and hits production on every dev-instance feed).
    export_production_snapshot.deploy(
        "search-vespa-dev-export-production-snapshot",
        work_pool_name=_WORK_POOL,
        image=DockerImage(
            name=image_name,
            tag="latest",
        ),
        job_variables=default_job_variables,
        parameters={
            "sample_percent": 100,
        },
        description="Snapshot production to s3://cpr-cache/search/vespa/index/ as sharded JSONL",
        cron="0 4 * * *",  # Once a day - see module docstring for why.
        build=False,
        push=False,
    )
    print("Deployed search-vespa-dev-export-production-snapshot")
