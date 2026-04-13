"""
Prefect deployment script for the vespa-feeder flows.

Creates one deployment per index.  Each deployment can be:
  - triggered on a schedule
  - triggered by another Prefect flow (call vespa_feed_flow directly)
  - triggered by an S3 event via a Prefect automation + webhook

Usage:
    uv run python deployments.py

Environment variables required:
    DOCKER_REGISTRY        - ECR registry URL
    PREFECT_API_URL        - Prefect Cloud / server URL
    PREFECT_API_KEY        - Prefect Cloud API key (if using Prefect Cloud)
"""

import importlib.metadata
import logging
import os
import subprocess
from typing import Any, ParamSpec, TypeVar

from prefect.docker.docker_image import DockerImage
from prefect.flows import Flow
from prefect.variables import Variable

from vespa_feeder.config import FeedJob
from vespa_feeder.flow import vespa_feed_flow

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

P = ParamSpec("P")
R = TypeVar("R")

MEGABYTES_PER_GIGABYTE = 1024
DEFAULT_JOB_VARIABLES = {
    "cpu": MEGABYTES_PER_GIGABYTE * 2,
    "memory": MEGABYTES_PER_GIGABYTE * 4,
    "ephemeralStorage": {"sizeInGiB": 30},
    "match_latest_revision_in_family": True,
}

# Indexes to deploy — one deployment per entry.
# s3_bucket / vespa_url / vespa_write_token are resolved from Prefect Variables at
# deploy time so they can be rotated without redeploying.
INDEXES: list[dict[str, Any]] = [
    {
        "index_name": "documents",
        "s3_key": "search/vespa/documents_feed_materializer.jsonl.gz",
        "description": "Feed documents index from S3 JSONL into Vespa",
        "schedule": "0 4 * * *",  # daily at 04:00 UTC
    },
    {
        "index_name": "documents-concepts",
        "s3_key": "search/vespa/documents_concepts_feed_materializer.jsonl.gz",
        "description": "Feed documents-concepts index from S3 JSONL into Vespa",
        "schedule": "0 4 * * *",
    },
    {
        "index_name": "labels",
        "s3_key": "search/vespa/labels_feed_materializer.jsonl.gz",
        "description": "Feed labels index from S3 JSONL into Vespa",
        "schedule": "0 4 * * *",
    },
    {
        "index_name": "passages",
        "s3_key": "search/vespa/passages_feed_materializer.jsonl.gz",
        "description": "Feed passages index from S3 JSONL into Vespa",
        "schedule": "0 4 * * 1",  # weekly, Monday 04:00 UTC
        "job_variables": DEFAULT_JOB_VARIABLES | {"ephemeralStorage": {"sizeInGiB": 100}},
    },
]


def _git_tags() -> list[str]:
    tags: list[str] = []
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        tags.append(f"sha:{sha}")
    except Exception as exc:
        logger.warning("Could not get git SHA: %s", exc)

    branch = os.environ.get("GIT_BRANCH")
    if not branch:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"]
            ).decode().strip()
        except Exception:
            pass
    if branch:
        tags.append(f"branch:{branch}")

    return tags


def create_deployment(
    flow: Flow[P, R],
    name: str,
    description: str,
    parameters: dict[str, Any],
    job_variables: dict[str, Any] = DEFAULT_JOB_VARIABLES,
    schedule: str | None = None,
) -> None:
    version = importlib.metadata.version("vespa-feeder")
    docker_registry = os.environ["DOCKER_REGISTRY"]
    image_name = f"{docker_registry}/vespa-feeder"

    work_pool_name = "mvp-prod-ecs"
    default_job_variables_name = "ecs-default-job-variables-prefect-mvp-prod"
    default_job_variables = Variable.get(default_job_variables_name)

    if not isinstance(default_job_variables, dict):
        raise ValueError(
            f"Prefect variable {default_job_variables_name!r} not found or is not a dict"
        )

    merged_job_variables = {**default_job_variables, **job_variables}
    tags = ["repo:vespa-feeder", "awsenv:prod"] + _git_tags()

    from prefect.schedules import Cron

    schedule_obj = (
        Cron(schedule, timezone="Europe/London", active=True) if schedule else None
    )

    flow.deploy(
        name,
        work_pool_name=work_pool_name,
        version=version,
        image=DockerImage(
            name=image_name,
            tag="latest",
            dockerfile="Dockerfile",
        ),
        job_variables=merged_job_variables,
        tags=tags,
        description=description,
        parameters=parameters,
        build=False,
        push=False,
        schedule=schedule_obj,
    )


def _resolve_feed_job(index_cfg: dict[str, Any]) -> FeedJob:
    """
    Resolve runtime secrets from Prefect Variables so they're not baked into
    the deployment definition.
    """
    s3_bucket = Variable.get("vespa_feeder_s3_bucket")
    vespa_url = Variable.get("vespa_feeder_vespa_url")
    vespa_write_token = Variable.get("vespa_feeder_vespa_write_token")

    return FeedJob(
        s3_bucket=str(s3_bucket),
        s3_key=index_cfg["s3_key"],
        vespa_url=str(vespa_url),
        vespa_write_token=str(vespa_write_token) if vespa_write_token else None,
        index_name=index_cfg["index_name"],
    )


if __name__ == "__main__":
    logger.info("vespa-feeder version: %s", importlib.metadata.version("vespa-feeder"))

    for cfg in INDEXES:
        job = _resolve_feed_job(cfg)
        create_deployment(
            flow=vespa_feed_flow,
            name=f"vespa-feed-{cfg['index_name']}-prod",
            description=cfg["description"],
            parameters={"job": job.model_dump()},
            job_variables=cfg.get("job_variables", DEFAULT_JOB_VARIABLES),
            schedule=cfg.get("schedule"),
        )
        logger.info("Deployed: vespa-feed-%s-prod", cfg["index_name"])
