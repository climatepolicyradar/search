"""
Shared resources for search API review stacks.

Creates long-lived infrastructure that ephemeral PR review stacks depend on:
- Shared ECR repository for review images (tagged per PR)
- Shared ECS cluster for review services
- Shared ECS IAM roles (avoids per-PR role creation)
- OIDC IAM role for Pulumi Deployments
- ESC environments providing AWS credentials
- Deployment settings for the review template stack

Deploy once to production; review stacks reference these outputs.
"""

import json
from typing import cast

import pulumi
import pulumi_aws as aws
import pulumi_pulumiservice as pulumiservice

org_name = "climatepolicyradar"
aws_account = aws.get_caller_identity()
account_id = aws_account.account_id

# ---------------------------------------------------------------------------
# OIDC Identity Provider (managed in aws_env, referenced here)
# ---------------------------------------------------------------------------
aws_env_stack = pulumi.StackReference(f"{org_name}/aws_env/production")
oidc_provider_arn = cast(str, aws_env_stack.get_output("production-oidc-provider-arn"))

# ---------------------------------------------------------------------------
# IAM Role for Pulumi Deployments (search review stacks)
# ---------------------------------------------------------------------------
deployment_role = aws.iam.Role(
    "production-search-pulumi-oidc-deployment-role",
    name="production-search-pulumi-oidc-deployment-role",
    description=(
        "Role for Pulumi Deployments and ESC to manage search review "
        "infrastructure via OIDC."
    ),
    assume_role_policy=pulumi.Output.from_input(oidc_provider_arn).apply(
        lambda provider_arn: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Federated": provider_arn},
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringLike": {
                                "api.pulumi.com/oidc:aud": [
                                    org_name,
                                    f"aws:{org_name}",
                                ],
                                "api.pulumi.com/oidc:sub": [
                                    f"pulumi:deploy:org:{org_name}:project:search:*",
                                    f"pulumi:environments:org:{org_name}:env:search/*",
                                    f"pulumi:deploy:org:{org_name}:project:search-review-stack-shared-resources:*",
                                    f"pulumi:environments:org:{org_name}:env:search-review-stack-shared-resources/*",
                                ],
                            },
                        },
                    }
                ],
            }
        )
    ),
    max_session_duration=3600,
    opts=pulumi.ResourceOptions(additional_secret_outputs=["arn"]),
)

aws.iam.RolePolicyAttachment(
    "production-search-deployment-role-admin-policy",
    role=deployment_role.name,
    policy_arn="arn:aws:iam::aws:policy/AdministratorAccess",
)

# ---------------------------------------------------------------------------
# Shared ECR Repository for Review Stacks
# ---------------------------------------------------------------------------
review_ecr_repo = aws.ecr.Repository(
    "review-search-api",
    name="review-search-api",
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=False,
    ),
    image_tag_mutability="MUTABLE",
    opts=pulumi.ResourceOptions(additional_secret_outputs=["repository_url"]),
)

# ---------------------------------------------------------------------------
# Shared ECS Cluster for Review Stacks
# ---------------------------------------------------------------------------
review_ecs_cluster = aws.ecs.Cluster(
    "search-review-ecs-cluster",
    name="search-review",
    settings=[
        aws.ecs.ClusterSettingArgs(
            name="containerInsights",
            value="enabled",
        )
    ],
)

# ---------------------------------------------------------------------------
# Shared ECS Task Role (runtime permissions: S3 read on production bucket)
# ---------------------------------------------------------------------------
review_ecs_task_role = aws.iam.Role(
    "shared-search-review-ecs-task-role",
    name="shared-search-review-ecs-task-role",
    description="Shared task role for search API review ECS services.",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
    max_session_duration=3600,
    opts=pulumi.ResourceOptions(additional_secret_outputs=["arn"]),
)

aws.iam.RolePolicy(
    "shared-search-review-task-role-s3-policy",
    role=review_ecs_task_role.id,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:ListBucket"],
                    "Resource": [
                        "arn:aws:s3:::cpr-production-search/*",
                        "arn:aws:s3:::cpr-production-search",
                    ],
                }
            ],
        }
    ),
)

# ---------------------------------------------------------------------------
# Shared ECS Task Execution Role (pulls image, injects secrets at startup)
# ---------------------------------------------------------------------------
review_ecs_task_execution_role = aws.iam.Role(
    "shared-search-review-ecs-task-execution-role",
    name="shared-search-review-ecs-task-execution-role",
    description="Shared task execution role for search API review ECS services.",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
    managed_policy_arns=[
        "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
    ],
    max_session_duration=3600,
    opts=pulumi.ResourceOptions(additional_secret_outputs=["arn"]),
)

# Grant SSM read access for production Vespa credentials.
aws.iam.RolePolicy(
    "shared-search-review-execution-role-ssm-policy",
    role=review_ecs_task_execution_role.id,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ssm:GetParameter", "ssm:GetParameters"],
                    "Resource": [
                        f"arn:aws:ssm:eu-west-1:{account_id}:parameter/search/vespa/endpoint",
                        f"arn:aws:ssm:eu-west-1:{account_id}:parameter/search/vespa/read_token",
                    ],
                }
            ],
        }
    ),
)

# ---------------------------------------------------------------------------
# Shared ECS Infrastructure Role (manages ALB, target groups, security groups)
# ---------------------------------------------------------------------------
review_ecs_infrastructure_role = aws.iam.Role(
    "shared-search-review-ecs-infrastructure-role",
    name="shared-search-review-ecs-infrastructure-role",
    description="Shared infrastructure role for search API review ECS services.",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
    managed_policy_arns=[
        "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices",
    ],
    max_session_duration=3600,
    opts=pulumi.ResourceOptions(additional_secret_outputs=["arn"]),
)

# ---------------------------------------------------------------------------
# ESC Environments
# ---------------------------------------------------------------------------
aws_creds_env_yaml = deployment_role.arn.apply(
    lambda role_arn: (
        "values:\n"
        "  aws:\n"
        "    login:\n"
        "      fn::open::aws-login:\n"
        "        oidc:\n"
        f"          roleArn: {role_arn}\n"
        "          sessionName: pulumi-search-review-deployments\n"
        "          duration: 1h\n"
        "  environmentVariables:\n"
        "    AWS_ACCESS_KEY_ID: ${aws.login.accessKeyId}\n"
        "    AWS_SECRET_ACCESS_KEY: ${aws.login.secretAccessKey}\n"
        "    AWS_SESSION_TOKEN: ${aws.login.sessionToken}\n"
        "    AWS_REGION: eu-west-1\n"
    )
)

aws_creds_env = pulumiservice.Environment(
    "aws-creds-production",
    organization=org_name,
    project="search-review-stack-shared-resources",
    name="aws-creds-production",
    yaml=aws_creds_env_yaml.apply(lambda y: pulumi.StringAsset(y)),
)

review_env_yaml = (
    "imports:\n"
    "  - search-review-stack-shared-resources/aws-creds-production\n"
    "\n"
    "values:\n"
    "  environmentVariables:\n"
    "    DEPLOY_FROM_MAIN_BRANCH_ONLY: 'false'\n"
    "    DEPLOY_TO_PROD_STACK_ALLOWED: 'false'\n"
)

pulumiservice.Environment(
    "search-review",
    organization=org_name,
    project="search",
    name="review",
    yaml=pulumi.StringAsset(review_env_yaml),
    opts=pulumi.ResourceOptions(depends_on=[aws_creds_env]),
)

# ---------------------------------------------------------------------------
# Deployment Settings for Review Template Stack
# ---------------------------------------------------------------------------
pulumiservice.DeploymentSettings(
    "search-review-deployment-settings",
    organization=org_name,
    project="search",
    stack="review",
    source_context=pulumiservice.DeploymentSettingsSourceContextArgs(
        git=pulumiservice.DeploymentSettingsGitSourceArgs(
            branch="main",
            repo_dir="infra",
        ),
    ),
    vcs=pulumiservice.DeploymentSettingsVcsArgs(
        provider="github",
        repository="climatepolicyradar/search",
        pull_request_template=False,
        deploy_commits=False,
        preview_pull_requests=False,
    ),
    operation_context=pulumiservice.DeploymentSettingsOperationContextArgs(
        options=pulumiservice.OperationContextOptionsArgs(
            skip_intermediate_deployments=True,
        ),
    ),
)

# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
pulumi.export("deployment_role_arn", deployment_role.arn)
pulumi.export("review_search_api_ecr_repository_url", review_ecr_repo.repository_url)
pulumi.export("review_ecs_cluster_arn", review_ecs_cluster.arn)
pulumi.export("review_ecs_task_role_arn", review_ecs_task_role.arn)
pulumi.export("review_ecs_task_execution_role_arn", review_ecs_task_execution_role.arn)
pulumi.export("review_ecs_infrastructure_role_arn", review_ecs_infrastructure_role.arn)
