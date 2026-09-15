"""
Prefect deployment for the vespa-feeder flows.

Run with: uv run python vespa-feeder/deployments.py
"""

from dataclasses import dataclass

import boto3
from documents_flow import (
    documents_concepts_feeder_flow,
    documents_feeder_flow,
    documents_principal_concepts_feeder_flow,
)
from labels_flow import labels_feeder_flow
from passages_flow import (
    passages_feeder_flow,
)
from prefect.docker import DockerImage
from prefect.variables import Variable

from prefect import Flow

_WORK_POOL = "mvp-prod-ecs"


@dataclass
class VespaFeederDeployment:
    """Prefect deployment for the vespa-feeder flows"""

    flow: Flow
    cron: str | None = None
    job_variables: dict | None = None


_FEEDS: list[VespaFeederDeployment] = [
    # Labels
    VespaFeederDeployment(flow=labels_feeder_flow, cron="0 5 * * *"),
    # Documents
    VespaFeederDeployment(
        flow=documents_feeder_flow,
        job_variables={"cpu": 1024, "memory": 2048},
        cron="0 5 * * *",
    ),
    # we've removed the cron to stop these tasks running on a schedule,
    # but keeping them as an escape hatch until we have had search running stable for a while.
    # TODO: remove these once we're happy `documents_feeder_flow` is stable.
    VespaFeederDeployment(flow=documents_concepts_feeder_flow),
    VespaFeederDeployment(flow=documents_principal_concepts_feeder_flow),
    # Passages
    # cpu=2048 was A/B tested against 1024 (same 8x2 connections default)
    # and showed no measurable difference (~8.2s CLI feed time either
    # way) - CPU isn't the constraint, so back to 1024. Combined with the
    # 8x2 vs 4x4 connections result (4x4 was 15% slower despite the same
    # total connection budget), the likely real ceiling is Vespa's
    # server-side feedapi-handler capacity, which 8x2=16 connections was
    # deliberately sized against.
    VespaFeederDeployment(
        flow=passages_feeder_flow,
        job_variables={"cpu": 1024, "memory": 4096},
        cron="0 5 * * *",
    ),
]

_DEFAULT_JOB_VARIABLES_NAME = "ecs-default-job-variables-prefect-mvp-prod"

if __name__ == "__main__":
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name
    image_name = f"{account_id}.dkr.ecr.{region}.amazonaws.com/search-vespa-feeder"

    default_job_variables = Variable.get(_DEFAULT_JOB_VARIABLES_NAME)
    if not isinstance(default_job_variables, dict):
        raise ValueError(
            f"Variable {_DEFAULT_JOB_VARIABLES_NAME} not found or is not a dict in Prefect"
        )

    for feed in _FEEDS:
        # These are and should be run after the other upstream pipeline deployments in ../deployments.py
        # at 3am
        # TODO: actual data flows based on events
        flow = feed.flow
        job_variables = {**default_job_variables, **(feed.job_variables or {})}
        flow.deploy(
            flow.name,
            work_pool_name=_WORK_POOL,
            image=DockerImage(
                name=image_name,
                tag="latest",
            ),
            job_variables=job_variables,
            cron=feed.cron,
            build=False,
            push=False,
        )
        print(f"Deployed {flow.name}")
