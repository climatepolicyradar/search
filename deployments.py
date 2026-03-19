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

from online_metrics.online_metrics_flow import collect_online_metrics
from relevance_tests import test_documents, test_labels, test_passages
from scripts.materialize_vespa_updates.from_data_in_api import (
    materialize_vespa_updates_from_data_in_api,
)
from scripts.materialize_vespa_updates.from_indexer_input import (
    materialize_vespa_updates_from_indexer_input,
)
from scripts.materialize_vespa_updates.from_inference_results import (
    materialize_vespa_updates_from_inference_results,
)
from search.vespa.documents_feed_flow import documents_feed_flow
from search.vespa.labels_feed_flow import labels_feed_flow
from search.vespa.passages_feed_flow import passages_feed_flow

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
    docker_repository = "search-prefect"
    image_name = f"{docker_registry}/{docker_repository}"

    work_pool_name = "mvp-prod-ecs"
    default_job_variables_name = "ecs-default-job-variables-prefect-mvp-prod"
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
            tag="latest",
            dockerfile="prefect/Dockerfile",
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

    # Running relevance tests
    rrule_relevance_tests = "RRULE:FREQ=MONTHLY;INTERVAL=1;BYDAY=-1MO;BYHOUR=21;BYMINUTE=0"  # last Monday of every month at 21:00

    rrule_online_metrics = "RRULE:FREQ=MONTHLY;INTERVAL=1;BYDAY=1MO;BYHOUR=21;BYMINUTE=0"  # first Monday of every month at 21:00

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

    # Online metrics
    create_deployment(
        flow=collect_online_metrics,
        description="Collect online metrics",
        rrule=rrule_online_metrics,
    )

    # Feeds
    create_deployment(
        flow=documents_feed_flow,
        description="Materialize documents feed",
        schedule="0 3 * * *",  # daily at 3am
        flow_variables=DEFAULT_FLOW_VARIABLES,
    )
    create_deployment(
        flow=labels_feed_flow,
        description="Materialize labels feed",
        schedule="0 3 * * *",  # daily at 3am
        flow_variables=DEFAULT_FLOW_VARIABLES,
    )

    create_deployment(
        flow=passages_feed_flow,
        description="Materialize passages feed",
        schedule="0 3 * * 1",  # weekly on Mondays at 3am
        flow_variables=DEFAULT_FLOW_VARIABLES
        | {"ephemeralStorage": {"sizeInGiB": 100}},  # bump storage for 100GB
    )

    # Materializers (to be deprecated with feed)
    create_deployment(
        flow=materialize_vespa_updates_from_indexer_input,
        description="Materialize Vespa update ops from indexer input bucket",
        schedule="0 3 * * *",  # daily at 3am
        flow_variables=DEFAULT_FLOW_VARIABLES
        | {"ephemeralStorage": {"sizeInGiB": 60}},  # bump storage for 40GB
    )

    create_deployment(
        flow=materialize_vespa_updates_from_data_in_api,
        description="Materialize Vespa update ops from data-in API",
        schedule="0 3 * * *",  # daily at 3am
        flow_variables=DEFAULT_FLOW_VARIABLES,
    )

    create_deployment(
        flow=materialize_vespa_updates_from_inference_results,
        description="Materialize Vespa update ops from inference results bucket",
        schedule="0 3 * * *",  # daily at 3am
        flow_variables=DEFAULT_FLOW_VARIABLES
        | {"ephemeralStorage": {"sizeInGiB": 60}},  # bump storage for 40GB
    )
