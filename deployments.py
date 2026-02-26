"""
Prefect deployment script for search flows.

Used to create server side representation of prefect flows, triggers, config, etc.
See: https://docs-2.prefect.io/latest/concepts/deployments/
"""

import importlib.metadata
import logging
import os
import subprocess
from typing import Any, ParamSpec, TypeVar

from prefect.docker.docker_image import DockerImage
from prefect.flows import Flow
from prefect.schedules import Cron
from prefect.variables import Variable

from relevance_tests import test_documents, test_labels, test_passages
from scripts.data_uploaders.upload_documents import upload_documents_databases
from scripts.data_uploaders.upload_labels import upload_labels_databases
from scripts.data_uploaders.upload_passages import upload_passages_databases

MEGABYTES_PER_GIGABYTE = 1024
DEFAULT_FLOW_VARIABLES = {
    "cpu": MEGABYTES_PER_GIGABYTE * 4,
    "memory": MEGABYTES_PER_GIGABYTE * 16,
    "ephemeralStorage": {"sizeInGiB": 50},
    "match_latest_revision_in_family": True,
}

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler and set level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Add ch to logger
logger.addHandler(ch)


# Match what Prefect uses for Flows:
#
# > .. we use the generic type variables `P` and `R` for "Parameters"
# > and "Returns" respectively.
P = ParamSpec("P")
R = TypeVar("R")


def create_deployment(
    flow: Flow[P, R],
    description: str,
    flow_variables: dict[str, Any] = DEFAULT_FLOW_VARIABLES,
    extra_tags: list[str] = [],
    schedule: str | None = None,
    **kwargs,
) -> None:
    """
    Create a deployment for the specified flow in the production environment.

    Parameters
    ----------
    flow : Flow[P, R]
        The Prefect flow to deploy
    description : str
        Description of what the flow does
    flow_variables : dict[str, Any], optional
        ECS task configuration (CPU, memory, etc.)
    extra_tags : list[str], optional
        Additional tags for the deployment
    schedule: str | None, optional
        Cron schedule for the deployed flow
    **kwargs:
        Are passed to flow.deploy
    """
    version = importlib.metadata.version("search")
    flow_name = flow.name
    docker_registry = os.environ["DOCKER_REGISTRY"]
    docker_repository = os.getenv("DOCKER_REPOSITORY", "search")
    image_name = os.path.join(docker_registry, docker_repository)

    work_pool_name = "mvp-prod-ecs"
    default_job_variables_name = "default-job-variables-prefect-mvp-prod"
    default_job_variables = Variable.get(default_job_variables_name)

    if not isinstance(default_job_variables, dict):
        raise ValueError(
            f"Variable {default_job_variables_name} not found or is not a dict in Prefect"
        )

    job_variables = {**default_job_variables, **flow_variables}
    tags = [f"repo:{docker_repository}", "awsenv:prod"] + extra_tags

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, check=True
        )
        if commit_sha := result.stdout.decode().strip():
            tags.append(f"sha:{commit_sha}")
    except Exception as e:
        logger.error(f"failed to get commit SHA: {e}")

    try:
        branch = os.environ.get("GIT_BRANCH")
        if not branch:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                check=True,
            )
            branch = result.stdout.decode().strip()

        if branch:
            tags.append(f"branch:{branch}")
    except Exception as e:
        logger.error(f"failed to get branch: {e}")

    schedule_obj = (
        Cron(
            schedule,
            timezone="Europe/London",
            active=True,
        )
        if schedule is not None
        else None
    )

    _ = flow.deploy(
        f"search-{flow_name}-prod",
        work_pool_name=work_pool_name,
        version=version,
        image=DockerImage(
            name=image_name,
            tag=version,
            dockerfile="Dockerfile",
        ),
        job_variables=job_variables,
        tags=tags,
        description=description,
        build=False,
        push=False,
        schedule=schedule_obj,
        **kwargs,
    )


if __name__ == "__main__":
    logger.info(f"using version: {importlib.metadata.version('search')}")

    # Data upload flows that load the full text data need more storage
    document_passage_flow_variables = DEFAULT_FLOW_VARIABLES | {
        "ephemeralStorage": {"sizeInGiB": 30}
    }

    # Uploading jsonl and duckdb for dev search endpoints
    create_deployment(
        flow=upload_documents_databases,
        description="Upload documents from HuggingFace to S3 as jsonl and duckdb",
        schedule="0 18 * * SUN",
        flow_variables=document_passage_flow_variables,
    )
    create_deployment(
        flow=upload_labels_databases,
        description="Upload labels from Wikibase to S3 as jsonl and duckdb",
        schedule="0 18 * * SUN",
    )
    create_deployment(
        flow=upload_passages_databases,
        description="Upload passages from HuggingFace to S3 as jsonl and duckdb",
        schedule="0 18 * * SUN",
        flow_variables=document_passage_flow_variables,
    )

    # Running relevance tests
    rrule_relevance_tests = "RRULE:FREQ=MONTHLY;INTERVAL=1;BYDAY=-1MO;BYHOUR=21;BYMINUTE=0"  # last Monday of every month at 21:00

    create_deployment(
        flow=test_documents.relevance_tests_documents,  # type: ignore
        description="Run relevance tests for documents",
        rrule=rrule_relevance_tests,
    )
    create_deployment(
        flow=test_labels.relevance_tests_labels,  # type: ignore
        description="Run relevance tests for labels",
        rrule=rrule_relevance_tests,
    )
    create_deployment(
        flow=test_passages.relevance_tests_passages,  # type: ignore
        description="Run relevance tests for passages",
        rrule=rrule_relevance_tests,
    )
