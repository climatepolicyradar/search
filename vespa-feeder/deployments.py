"""
Prefect deployment for the vespa-feeder flows.

Run with: `just deploy` from vespa-feeder/
"""

from dataclasses import dataclass

import boto3
from prefect.client.schemas.objects import (
    ConcurrencyLimitConfig,
    ConcurrencyLimitStrategy,
)
from prefect.docker import DockerImage
from prefect.schedules import Cron
from prefect.types.entrypoint import EntrypointType
from prefect.variables import Variable
from vespa_feeder.documents.flow import documents_feeder_flow
from vespa_feeder.labels.flow import labels_feeder_flow
from vespa_feeder.passages.flow import passages_feeder_flow

from prefect import Flow

_WORK_POOL = "mvp-prod-ecs"

# A document or passages feed takes hours, so a run that degrades or
# hangs is still going when the next day's schedule fires. Two concurrent feeds
# double the connection load on Vespa and, because both feed the same
# documents from different export snapshots, and it's ambiguous which write wins.
# We ENQUEUE rather than CANCEL_NEW so we don't silently skip any day. A late run
# waits and starts when the one in flight finishes.
_CONCURRENCY_LIMIT = ConcurrencyLimitConfig(
    limit=1,
    collision_strategy=ConcurrencyLimitStrategy.ENQUEUE,
)


@dataclass
class VespaFeederDeployment:
    """Prefect deployment for the vespa-feeder flows"""

    flow: Flow
    cron: str


_FEEDS: list[VespaFeederDeployment] = [
    VespaFeederDeployment(flow=labels_feeder_flow, cron="30 8 * * *"),
    VespaFeederDeployment(flow=documents_feeder_flow, cron="30 8 * * *"),
    VespaFeederDeployment(flow=passages_feeder_flow, cron="30 8 * * *"),
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
        flow.deploy(
            name=flow.name,
            work_pool_name=_WORK_POOL,
            image=DockerImage(
                name=image_name,
                tag="latest",
            ),
            job_variables=default_job_variables,
            concurrency_limit=_CONCURRENCY_LIMIT,
            schedule=Cron(feed.cron, slug=flow.name),
            build=False,
            push=False,
            entrypoint_type=EntrypointType.MODULE_PATH,
        )
        print(f"Deployed {flow.name}")
