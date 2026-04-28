"""
Prefect deployment for the vespa-feeder flows.

Run with: uv run python vespa-feeder/deployments.py
"""

import boto3
from flow import vespa_feeder_flow
from prefect.docker import DockerImage
from prefect.variables import Variable

WORK_POOL = "mvp-prod-ecs"
S3_BUCKET = "cpr-cache"

FEEDS = [
    # Labels
    {
        "name": "search-vespa-feeder-labels",
        "s3_key": "search/vespa/labels_feed_materializer.jsonl",
        "description": "Feed labels JSONL from S3 into Vespa",
    },
    # Documents
    {
        "name": "search-vespa-feeder-documents",
        "s3_key": "search/vespa/documents_feed_materializer.jsonl",
        "description": "Feed documents JSONL from S3 into Vespa",
    },
    {
        "name": "search-vespa-feeder-documents-concepts",
        "s3_key": "search/vespa/documents_concepts_feed_materializer.jsonl",
        "description": "Feed documents concepts JSONL from S3 into Vespa",
    },
    {
        "name": "search-vespa-feeder-documents-principal-concepts",
        "s3_key": "search/vespa/documents_principal_concepts_feed_materializer.jsonl",
        "description": "Feed documents principal concepts JSONL from S3 into Vespa",
    },
    # Passages
    {
        "name": "search-vespa-feeder-passages",
        "s3_key": "search/vespa/passages_feed_materializer.jsonl",
        "description": "Feed passages JSONL from S3 into Vespa",
    },
]

DEFAULT_JOB_VARIABLES_NAME = "ecs-default-job-variables-prefect-mvp-prod"

if __name__ == "__main__":
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = boto3.session.Session().region_name
    image_name = f"{account_id}.dkr.ecr.{region}.amazonaws.com/search-vespa-feeder"

    default_job_variables = Variable.get(DEFAULT_JOB_VARIABLES_NAME)
    if not isinstance(default_job_variables, dict):
        raise ValueError(
            f"Variable {DEFAULT_JOB_VARIABLES_NAME} not found or is not a dict in Prefect"
        )

    for feed in FEEDS:
        # These are and should be run after the other upstream pipeline deployments in ../deployments.py
        # at 3am
        # TODO: actual data flows based on events
        vespa_feeder_flow.deploy(
            feed["name"],
            work_pool_name=WORK_POOL,
            image=DockerImage(
                name=image_name,
                tag="latest",
            ),
            job_variables=default_job_variables,
            parameters={
                "s3_bucket": S3_BUCKET,
                "s3_key": feed["s3_key"],
            },
            description=feed["description"],
            cron="0 5 * * *",  # 5 AM daily.
            build=False,
            push=False,
        )
        print(f"Deployed {feed['name']}")
