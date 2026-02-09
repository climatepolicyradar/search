"""AWS infrastructure for the Search API using Pulumi."""

import json

import pulumi
from pulumi_aws import apprunner, ecr, get_caller_identity, iam, s3

from search.config import REPO_ROOT_DIR, get_git_commit_hash

# pulumi config
config = pulumi.Config()
caller_identity = get_caller_identity()
account_id = caller_identity.account_id
stack = pulumi.get_stack()

# Get the git commit hash for tagging the image
GIT_COMMIT_HASH = get_git_commit_hash()

application_name = "search-api"
dockerfile_path = REPO_ROOT_DIR / "api" / "Dockerfile"

# we don't namespace this bucket with search-api as it is more broadly search
bucket = s3.Bucket(
    "search-bucket",
    bucket=f"cpr-{stack}-search",
)

# Create a private ECR repository to store the Docker image
repo = ecr.Repository(
    f"{application_name}-repo",
    name=f"{application_name}",
    image_scanning_configuration=ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    image_tag_mutability="MUTABLE",
)

# AppRunner
apprunner_ecr_role = iam.Role(
    f"{application_name}-apprunner-ecr-role",
    name=f"{application_name}-apprunner-ecr-role",
    description="IAM role for AppRunner",
    assume_role_policy=iam.get_policy_document(
        statements=[
            iam.GetPolicyDocumentStatementArgs(
                effect="Allow",
                principals=[
                    iam.GetPolicyDocumentStatementPrincipalArgs(
                        type="Service",
                        identifiers=["build.apprunner.amazonaws.com"],
                    )
                ],
                actions=["sts:AssumeRole"],
            )
        ]
    ).json,
)
apprunner_ecr_role_policy = iam.RolePolicy(
    f"{application_name}-apprunner-ecr-role-policy",
    name=f"{application_name}-apprunner-ecr-role-policy",
    role=apprunner_ecr_role.id,
    policy=iam.get_policy_document(
        statements=[
            iam.GetPolicyDocumentStatementArgs(
                effect="Allow",
                actions=[
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:DescribeImages",
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                ],
                resources=["*"],
            )
        ]
    ).json,
)
apprunner_instance_role = iam.Role(
    f"{application_name}-apprunner-instance-role",
    name=f"{application_name}-apprunner-instance-role",
    assume_role_policy=iam.get_policy_document(
        statements=[
            iam.GetPolicyDocumentStatementArgs(
                effect="Allow",
                principals=[
                    iam.GetPolicyDocumentStatementPrincipalArgs(
                        type="Service",
                        identifiers=["tasks.apprunner.amazonaws.com"],
                    )
                ],
                actions=["sts:AssumeRole"],
            )
        ]
    ).json,
)
apprunner_read_s3_policy = iam.Policy(
    f"{application_name}-read-s3-policy",
    name=f"{application_name}-read-s3-policy",
    description="Policy to allow reading data files from S3",
    policy=pulumi.Output.all(bucket.arn).apply(
        lambda arns: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Resource": [f"{arns[0]}/*", arns[0]],
                    }
                ],
            }
        )
    ),
)
apprunner_read_s3_policy_attachment = iam.RolePolicyAttachment(
    f"{application_name}-apprunner-reads3-policy-attachment",
    role=apprunner_instance_role.name,
    policy_arn=apprunner_read_s3_policy.arn,
)

apprunner_service = apprunner.Service(
    f"{application_name}-apprunner-service",
    service_name=f"{application_name}",
    source_configuration=apprunner.ServiceSourceConfigurationArgs(
        authentication_configuration=apprunner.ServiceSourceConfigurationAuthenticationConfigurationArgs(
            access_role_arn=apprunner_ecr_role.arn,
        ),
        image_repository=apprunner.ServiceSourceConfigurationImageRepositoryArgs(
            image_identifier=repo.repository_url.apply(lambda url: f"{url}:latest"),
            image_repository_type="ECR",
            image_configuration=apprunner.ServiceSourceConfigurationImageRepositoryImageConfigurationArgs(
                port="8080",
                runtime_environment_variables={
                    "BUCKET_NAME": bucket.bucket,
                },
            ),
        ),
    ),
    health_check_configuration=apprunner.ServiceHealthCheckConfigurationArgs(
        protocol="HTTP",
        path="/",
        interval=10,
        timeout=5,
        healthy_threshold=1,
        unhealthy_threshold=2,
    ),
    network_configuration=apprunner.ServiceNetworkConfigurationArgs(
        ingress_configuration=apprunner.ServiceNetworkConfigurationIngressConfigurationArgs(
            is_publicly_accessible=True,
        ),
        ip_address_type="IPV4",
    ),
    instance_configuration=apprunner.ServiceInstanceConfigurationArgs(
        instance_role_arn=apprunner_instance_role.arn,
    ),
)


# Export useful outputs
pulumi.export("bucket_name", bucket.id)
pulumi.export("apprunner_service_service_url", apprunner_service.service_url)
