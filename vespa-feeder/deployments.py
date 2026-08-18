"""
Prefect deployment for the vespa-feeder flows.

Run with: uv run python vespa-feeder/deployments.py
"""

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

_WORK_POOL = "mvp-prod-ecs"

_FEEDS = [
    # Labels
    {"flow": labels_feeder_flow},
    # Documents
    {"flow": documents_feeder_flow, "job_variables": {"cpu": 1024, "memory": 2048}},
    {"flow": documents_concepts_feeder_flow},
    {"flow": documents_principal_concepts_feeder_flow},
    # Passages
    # cpu=2048 was A/B tested against 1024 (same 8x2 connections default)
    # and showed no measurable difference (~8.2s CLI feed time either
    # way) - CPU isn't the constraint, so back to 1024. Combined with the
    # 8x2 vs 4x4 connections result (4x4 was 15% slower despite the same
    # total connection budget), the likely real ceiling is Vespa's
    # server-side feedapi-handler capacity, which 8x2=16 connections was
    # deliberately sized against.
    {
        "flow": passages_feeder_flow,
        "job_variables": {"cpu": 1024, "memory": 4096},
    },
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
        flow = feed["flow"]
        job_variables = {**default_job_variables, **feed.get("job_variables", {})}
        flow.deploy(
            flow.name,
            work_pool_name=_WORK_POOL,
            image=DockerImage(
                name=image_name,
                tag="latest",
            ),
            job_variables=job_variables,
            cron="0 5 * * *",  # 5 AM daily.
            build=False,
            push=False,
        )
        print(f"Deployed {flow.name}")
