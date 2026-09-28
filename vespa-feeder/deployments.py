"""
Prefect deployment for the vespa-feeder flows.

Run with: uv run python vespa-feeder/deployments.py
"""

from dataclasses import dataclass

import boto3
from documents_flow import documents_feeder_flow
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
    # Adding a `variant` will deploy to `{flow.name}/{flow.name}::{variant}`
    # which will allow you to a/b test flows.
    variant: str | None = None
    # e.g. parameters.sample_rate = 0.1 will get a determanist sample
    # to avoid long running tests.
    # e.g. parameters.s3_key = "20260922T190625Z" will ensure you always have the same
    # data across tests.
    # This will not work for labels
    # @related: LABEL_RELATIONSHIPS_DO_NOT_EXIST
    parameters: dict | None = None
    # an example of an a/b test could be
    # VespaFeederDeployment(
    #     flow=passages_feeder_flow,
    #     variant="batch-1",
    #     job_variables={
    #         "cpu": 1024,
    #         "memory": 4096,
    #         "ephemeralStorage": {"sizeInGiB": 50},
    #     },
    #     parameters={
    #         "batch_size": 1,
    #         "sample_rate": 0.1,
    #         "s3_key": "20260922T190625Z",
    #     },
    # ),
    # VespaFeederDeployment(
    #     flow=passages_feeder_flow,
    #     variant="batch-5",
    #     job_variables={
    #         "cpu": 2048,
    #         "memory": 8192,
    #         "ephemeralStorage": {"sizeInGiB": 50},
    #     },
    #     parameters={
    #         "batch_size": 5,
    #         "sample_rate": 0.1,
    #         "s3_key": "20260922T190625Z",
    #     },
    # )


_FEEDS: list[VespaFeederDeployment] = [
    # Labels
    VespaFeederDeployment(flow=labels_feeder_flow, cron="0 5 * * *"),
    # Documents
    VespaFeederDeployment(
        flow=documents_feeder_flow,
        job_variables={"cpu": 1024, "memory": 2048},
    ),
    # Passages
    VespaFeederDeployment(
        flow=passages_feeder_flow,
        # 8 x 10 x 47MB x 2 = 7.5GB worst case.
        job_variables={
            "cpu": 2048,
            "memory": 16384,
            "ephemeralStorage": {"sizeInGiB": 50},
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
