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
    passages_feeder_flow_v2,
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
    variant: str | None = None
    parameters: dict | None = None


# 10% of 6050 files = 605, enough to fill 8 workers several times over at
# every batch size under test while keeping a variant to ~30 minutes.
_AB_SAMPLE_RATE = 0.1

# An immutable s3_key, not latest/ - latest/ is rewritten in place and
# variants must feed identical data to be comparable.
_AB_S3_KEY = "20260922T190625Z"

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
    # v2 A/B variants. v2 stages a whole batch before feeding it, so a task
    # holds max_workers x batch_size files on disk at once (source AND
    # derived), where the source files average 16MB and reach 47MB:
    #
    #   peak bytes = max_workers(8) x batch_size x file_size x 2
    #
    # Memory is sized off the 47MB worst case, not the average, because the
    # 2026-09-23 run OOMed on exactly that - see the sizing note per variant.
    # Nothing is scheduled: run them by hand, one at a time, so they are not
    # competing for the same Vespa feedapi-handler capacity.
    #
    # v1 is the control at 19.7 files/min. Both v2 runs so far were SLOWER
    # (15.4 at batch_size=50, 16.6 at batch_size=10) while resource-starved,
    # so the question these answer is whether batching beats v1 at all.
    VespaFeederDeployment(
        flow=passages_feeder_flow_v2,
        variant="batch-1",
        # 8 x 1 x 47MB x 2 = 0.8GB worst case. Matches v1's footprint, so it
        # isolates the batched `vespa feed` call from the staging change.
        job_variables={
            "cpu": 1024,
            "memory": 4096,
            "ephemeralStorage": {"sizeInGiB": 50},
        },
        parameters={
            "batch_size": 1,
            "sample_rate": _AB_SAMPLE_RATE,
            "s3_key": _AB_S3_KEY,
        },
    ),
    VespaFeederDeployment(
        flow=passages_feeder_flow_v2,
        variant="batch-5",
        # 8 x 5 x 47MB x 2 = 3.8GB worst case.
        job_variables={
            "cpu": 2048,
            "memory": 8192,
            "ephemeralStorage": {"sizeInGiB": 50},
        },
        parameters={
            "batch_size": 5,
            "sample_rate": _AB_SAMPLE_RATE,
            "s3_key": _AB_S3_KEY,
        },
    ),
    VespaFeederDeployment(
        flow=passages_feeder_flow_v2,
        variant="batch-10",
        # 8 x 10 x 47MB x 2 = 7.5GB worst case.
        job_variables={
            "cpu": 2048,
            "memory": 16384,
            "ephemeralStorage": {"sizeInGiB": 50},
        },
        parameters={
            "batch_size": 10,
            "sample_rate": _AB_SAMPLE_RATE,
            "s3_key": _AB_S3_KEY,
        },
    ),
    VespaFeederDeployment(
        flow=passages_feeder_flow_v2,
        variant="batch-25",
        # 8 x 25 x 47MB x 2 = 18.8GB worst case, so this needs cpu=4096 to
        # reach a memory tier above 16GB at all.
        job_variables={
            "cpu": 4096,
            "memory": 24576,
            "ephemeralStorage": {"sizeInGiB": 100},
        },
        parameters={
            "batch_size": 25,
            "sample_rate": _AB_SAMPLE_RATE,
            "s3_key": _AB_S3_KEY,
        },
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
        deployment_name = f"{flow.name}:{feed.variant}" if feed.variant else flow.name
        job_variables = {**default_job_variables, **(feed.job_variables or {})}
        flow.deploy(
            name=deployment_name,
            work_pool_name=_WORK_POOL,
            image=DockerImage(
                name=image_name,
                tag="latest",
            ),
            job_variables=job_variables,
            parameters=feed.parameters,
            cron=feed.cron,
            build=False,
            push=False,
        )
        print(f"Deployed {deployment_name}")
