"""AWS infrastructure for the Search API using Pulumi."""

import json
import re

import components.aws as components_aws
import pulumi
import pulumi_docker_build as docker_build
from pulumi_aws import (
    apprunner,
    ecr,
    ecs,
    get_caller_identity,
    iam,
    s3,
    ssm,
)
from pulumi_aws.ecs.express_gateway_service import (
    ExpressGatewayService,
    ExpressGatewayServicePrimaryContainerArgs,
    ExpressGatewayServicePrimaryContainerEnvironmentArgs,
    ExpressGatewayServicePrimaryContainerSecretArgs,
    ExpressGatewayServiceScalingTargetArgs,
)

from search.config import (
    REPO_ROOT_DIR,
    get_git_commit_hash,
    vespa_private_key_read_only_ssm_key,
    vespa_public_cert_read_only_ssm_key,
    vespa_url_ssm_key,
    wikibase_password_ssm_key,
    wikibase_url_ssm_key,
    wikibase_username_ssm_key,
)

# pulumi config
config = pulumi.Config()
caller_identity = get_caller_identity()
account_id = caller_identity.account_id
stack = pulumi.get_stack()
name = pulumi.get_project()

tags = {
    "CPR-Created-By": "pulumi",
    "CPR-Pulumi-Stack-Name": stack,
    "CPR-Pulumi-Project-Name": pulumi.get_project(),
    "CPR-Tag": f"{stack}-{name}",
    "Environment": stack,
}

application_name = "search-api"
dockerfile_path = REPO_ROOT_DIR / "api" / "Dockerfile"

is_review_stack = stack.startswith("pr-")

if is_review_stack:
    # ------------------------------------------------------------------
    # Review stack: build image, create ECS service using shared resources
    # ------------------------------------------------------------------
    pr_match = re.search(r"(\d+)$", stack)
    pr_number = pr_match.group(1) if pr_match else stack

    org_name = "climatepolicyradar"
    shared_resources = pulumi.StackReference(
        f"{org_name}/search-review-stack-shared-resources/production"
    )

    shared_ecr_url = shared_resources.get_output("review_search_api_ecr_repository_url")
    shared_cluster_arn = shared_resources.get_output("review_ecs_cluster_arn")
    shared_task_role_arn = shared_resources.get_output("review_ecs_task_role_arn")
    shared_execution_role_arn = shared_resources.get_output(
        "review_ecs_task_execution_role_arn"
    )
    shared_infrastructure_role_arn = shared_resources.get_output(
        "review_ecs_infrastructure_role_arn"
    )

    ecr_auth = ecr.get_authorization_token_output()

    review_image = docker_build.Image(
        "review-search-api-image",
        tags=[pulumi.Output.concat(shared_ecr_url, ":", stack)],
        context=docker_build.BuildContextArgs(location=str(REPO_ROOT_DIR)),
        dockerfile=docker_build.DockerfileArgs(location=str(dockerfile_path)),
        platforms=[docker_build.Platform.LINUX_AMD64],
        push=True,
        registries=[
            docker_build.RegistryArgs(
                address=shared_ecr_url,
                username=ecr_auth.user_name,
                password=ecr_auth.password,
            ),
        ],
        build_on_preview=False,
    )

    prod_vespa_endpoint_arn = (
        f"arn:aws:ssm:eu-west-1:{account_id}:parameter/search/vespa/endpoint"
    )
    prod_vespa_read_token_arn = (
        f"arn:aws:ssm:eu-west-1:{account_id}:parameter/search/vespa/read_token"
    )

    review_ecs_service = ExpressGatewayService(
        "review-search-api-ecs-express-service",
        service_name=stack,
        cluster=shared_cluster_arn,
        execution_role_arn=shared_execution_role_arn,
        infrastructure_role_arn=shared_infrastructure_role_arn,
        task_role_arn=shared_task_role_arn,
        primary_container=ExpressGatewayServicePrimaryContainerArgs(
            image=pulumi.Output.concat(shared_ecr_url, ":", stack),
            container_port=8080,
            environments=[
                ExpressGatewayServicePrimaryContainerEnvironmentArgs(
                    name="BUCKET_NAME", value="cpr-production-search"
                ),
                ExpressGatewayServicePrimaryContainerEnvironmentArgs(
                    name="ENV", value=stack
                ),
            ],
            secrets=[
                ExpressGatewayServicePrimaryContainerSecretArgs(
                    name="VESPA_ENDPOINT", value_from=prod_vespa_endpoint_arn
                ),
                ExpressGatewayServicePrimaryContainerSecretArgs(
                    name="VESPA_READ_TOKEN", value_from=prod_vespa_read_token_arn
                ),
            ],
        ),
        health_check_path="/",
        cpu="1024",
        memory="2048",
        scaling_targets=[
            ExpressGatewayServiceScalingTargetArgs(
                auto_scaling_metric="AVERAGE_CPU",
                auto_scaling_target_value=70,
                min_task_count=1,
                max_task_count=1,
            ),
        ],
        tags={"Environment": "review", "PRNumber": pr_number},
        opts=pulumi.ResourceOptions(depends_on=[review_image]),
    )

    pulumi.export(
        "review_service_url",
        review_ecs_service.ingress_paths.apply(
            lambda paths: paths[0].endpoint if paths else None
        ),
    )

elif stack != "review":
    # ------------------------------------------------------------------
    # Production stack: full infrastructure
    # ------------------------------------------------------------------

    # Get the git commit hash for tagging the image
    GIT_COMMIT_HASH = get_git_commit_hash()

    # we don't namespace this bucket with search-api as it is more broadly search
    bucket = s3.Bucket(
        "search-bucket",
        bucket=f"cpr-{stack}-search",
    )

    bucket_versioning = s3.BucketVersioning(
        "search-bucket-versioning",
        bucket=bucket.id,
        versioning_configuration=s3.BucketVersioningVersioningConfigurationArgs(
            status="Enabled",
        ),
    )

    bucket_lifecycle = s3.BucketLifecycleConfiguration(
        "search-bucket-lifecycle",
        bucket=bucket.id,
        rules=[
            s3.BucketLifecycleConfigurationRuleArgs(
                id="noncurrent-version-cleanup-90d",
                status="Enabled",
                noncurrent_version_expiration=s3.BucketLifecycleConfigurationRuleNoncurrentVersionExpirationArgs(
                    noncurrent_days=90,
                ),
            ),
        ],
        opts=pulumi.ResourceOptions(depends_on=[bucket_versioning]),
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
                ),
            ]
        ).json,
    )
    vespa_endpoint = ssm.Parameter(
        "vespa-endpoint",
        name="/search/vespa/endpoint",
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("vespa_endpoint"),
    )

    vespa_read_token = ssm.Parameter(
        "vespa-read-token",
        name="/search/vespa/read_token",
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("vespa_read_token"),
    )

    # Used by vespa-dev/feed_from_production.py's feed_target task, run on the
    # Prefect ECS work pool (mvp-prod-ecs) - not provisioned by this stack, so its
    # task role isn't granted read access here. See vespa/app/services.xml for the
    # search-dev-scoped client this token authenticates against, and
    # vespa-dev/justfile's `create`/`destroy` recipes for the per-instance
    # endpoint (/search/vespa-dev/<instance>) this token is paired with.
    vespa_dev_read_token = ssm.Parameter(
        "vespa-dev-read-token",
        name="/search/vespa-dev/read_token",
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("vespa_dev_read_token"),
    )
    vespa_dev_write_token = ssm.Parameter(
        "vespa-dev-write-token",
        name="/search/vespa-dev/write_token",
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("vespa_dev_write_token"),
    )

    apprunner_ssm_parameter_policy = iam.RolePolicy(
        f"{application_name}-ssm-parameter-policy",
        name=f"{application_name}-ssm-parameter-policy",
        role=apprunner_instance_role.name,
        policy=pulumi.Output.all(
            vespa_endpoint_arn=vespa_endpoint.arn,
            vespa_read_token_arn=vespa_read_token.arn,
            vespa_dev_write_token_arn=vespa_dev_write_token.arn,
        ).apply(
            lambda args: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "ssm:GetParameter",
                                "ssm:GetParameters",
                                "ssm:DescribeParameters",
                            ],
                            "Resource": [
                                args["vespa_endpoint_arn"],
                                args["vespa_read_token_arn"],
                                args["vespa_dev_write_token_arn"],
                            ],
                        }
                    ],
                }
            )
        ),
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
                        "ENV": stack,
                    },
                    runtime_environment_secrets={
                        "VESPA_ENDPOINT": vespa_endpoint.arn,
                        "VESPA_READ_TOKEN": vespa_read_token.arn,
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

    search_api_github_actions_role = iam.Role(
        f"{name}-{stack}-github-actions",
        assume_role_policy=json.dumps(
            {
                "Statement": [
                    {
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringEquals": {
                                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                            },
                            "StringLike": {
                                "token.actions.githubusercontent.com:sub": "repo:climatepolicyradar/search:*"
                            },
                        },
                        "Effect": "Allow",
                        "Principal": {
                            "Federated": f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
                        },
                    }
                ],
                "Version": "2012-10-17",
            }
        ),
        inline_policies=[
            {
                "name": f"{name}-{stack}-github-actions",
                "policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Action": [
                                    "ecr:GetAuthorizationToken",
                                    "ecr:InitiateLayerUpload",
                                    "ecr:UploadLayerPart",
                                    "ecr:CompleteLayerUpload",
                                    "ecr:PutImage",
                                    "iam:PassRole",
                                    "ecr:DescribeRepositories",
                                    "ecr:CreateRepository",
                                    "ecr:BatchGetImage",
                                    "ecr:BatchCheckLayerAvailability",
                                    "ecr:DescribeImages",
                                    "ecr:GetDownloadUrlForLayer",
                                    "ecr:ListImages",
                                    "iam:ListAccountAliases",
                                    "iam:GetPolicy",
                                    "iam:GetRole",
                                    "acm:DescribeCertificate",
                                    # used for ECS deployment
                                    "ecs:DescribeServices",
                                    "ecs:DescribeExpressGatewayService",
                                    "ecs:CreateExpressGatewayService",
                                    "ecs:UpdateExpressGatewayService",
                                    "ecs:CreateCluster",
                                    "ecs:RegisterTaskDefinition",
                                    "ecs:ListServiceDeployments",
                                    "ecs:DescribeServiceDeployments",
                                ],
                                "Effect": "Allow",
                                "Resource": "*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": "sts:AssumeRole",
                                "Resource": [
                                    f"arn:aws:iam::{account_id}:role/{application_name}-ecs-infrastructure-role",
                                    f"arn:aws:iam::{account_id}:role/{application_name}-ecs-task-execution-role",
                                ],
                            },
                        ],
                    }
                ),
            }
        ],
        name=f"{name}-{stack}-github-actions",
        tags=tags,
        opts=pulumi.ResourceOptions(protect=True),
    )

    # -----
    # SSM
    # -----

    vespa_url_ssm = ssm.Parameter(
        vespa_url_ssm_key,
        name=vespa_url_ssm_key,
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("VESPA_URL"),
    )

    vespa_private_key_read_only_ssm = ssm.Parameter(
        vespa_private_key_read_only_ssm_key,
        name=vespa_private_key_read_only_ssm_key,
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("VESPA_PRIVATE_KEY_READ_ONLY"),
    )

    vespa_public_cert_read_only_ssm = ssm.Parameter(
        vespa_public_cert_read_only_ssm_key,
        name=vespa_public_cert_read_only_ssm_key,
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("VESPA_PUBLIC_CERT_READ_ONLY"),
    )

    wikibase_url_ssm = ssm.Parameter(
        wikibase_url_ssm_key,
        name=wikibase_url_ssm_key,
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("WIKIBASE_URL"),
    )

    wikibase_username_ssm = ssm.Parameter(
        wikibase_username_ssm_key,
        name=wikibase_username_ssm_key,
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("WIKIBASE_USERNAME"),
    )

    wikibase_password_ssm = ssm.Parameter(
        wikibase_password_ssm_key,
        name=wikibase_password_ssm_key,
        type=ssm.ParameterType.SECURE_STRING,
        value=config.get("WIKIBASE_PASSWORD"),
    )

    # These exports are the public API for this stack, and consumed by external stacks
    # Edit with caution
    pulumi.export("apprunner_service_url", apprunner_service.service_url)

    # -----
    # ECS Express Mode (running in parallel with AppRunner during migration)
    # -----

    # Task role: runtime permissions (S3 read) — reuses the same policy as AppRunner
    ecs_task_role = iam.Role(
        f"{application_name}-ecs-task-role",
        name=f"{application_name}-ecs-task-role",
        assume_role_policy=iam.get_policy_document(
            statements=[
                iam.GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        iam.GetPolicyDocumentStatementPrincipalArgs(
                            type="Service",
                            identifiers=["ecs-tasks.amazonaws.com"],
                        )
                    ],
                    actions=["sts:AssumeRole"],
                )
            ]
        ).json,
    )
    iam.RolePolicyAttachment(
        f"{application_name}-ecs-task-reads3-policy-attachment",
        role=ecs_task_role.name,
        policy_arn=apprunner_read_s3_policy.arn,
    )

    # Execution role: pulls the image and injects secrets at container startup
    ecs_task_execution_role = iam.Role(
        f"{application_name}-ecs-task-execution-role",
        name=f"{application_name}-ecs-task-execution-role",
        assume_role_policy=iam.get_policy_document(
            statements=[
                iam.GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        iam.GetPolicyDocumentStatementPrincipalArgs(
                            type="Service",
                            identifiers=["ecs-tasks.amazonaws.com"],
                        )
                    ],
                    actions=["sts:AssumeRole"],
                ),
                iam.GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        iam.GetPolicyDocumentStatementPrincipalArgs(
                            type="AWS",
                            identifiers=[
                                f"arn:aws:iam::{account_id}:role/{name}-{stack}-github-actions"
                            ],
                        )
                    ],
                    actions=["sts:AssumeRole"],
                ),
            ]
        ).json,
        managed_policy_arns=[
            "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
        ],
    )
    iam.RolePolicy(
        f"{application_name}-ecs-execution-ssm-policy",
        name=f"{application_name}-ecs-execution-ssm-policy",
        role=ecs_task_execution_role.name,
        policy=pulumi.Output.all(
            vespa_endpoint_arn=vespa_endpoint.arn,
            vespa_read_token_arn=vespa_read_token.arn,
        ).apply(
            lambda args: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["ssm:GetParameter", "ssm:GetParameters"],
                            "Resource": [
                                args["vespa_endpoint_arn"],
                                args["vespa_read_token_arn"],
                            ],
                        }
                    ],
                }
            )
        ),
    )

    # Infrastructure role: manages the ALB, target groups, and security groups
    ecs_infrastructure_role = iam.Role(
        f"{application_name}-ecs-infrastructure-role",
        name=f"{application_name}-ecs-infrastructure-role",
        assume_role_policy=iam.get_policy_document(
            statements=[
                iam.GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        iam.GetPolicyDocumentStatementPrincipalArgs(
                            type="Service",
                            identifiers=["ecs.amazonaws.com"],
                        )
                    ],
                    actions=["sts:AssumeRole"],
                ),
                iam.GetPolicyDocumentStatementArgs(
                    effect="Allow",
                    principals=[
                        iam.GetPolicyDocumentStatementPrincipalArgs(
                            type="AWS",
                            identifiers=[
                                f"arn:aws:iam::{account_id}:role/{name}-{stack}-github-actions"
                            ],
                        )
                    ],
                    actions=["sts:AssumeRole"],
                ),
            ]
        ).json,
        managed_policy_arns=[
            "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices",
        ],
    )

    ecs_cluster = ecs.Cluster(
        f"{application_name}-ecs-cluster",
        name="search",
        settings=[
            ecs.ClusterSettingArgs(
                name="containerInsights",
                value="enabled",
            )
        ],
    )

    ecs_express_service = ExpressGatewayService(
        f"{application_name}-ecs-express-service",
        service_name=application_name,
        cluster=ecs_cluster.arn,
        execution_role_arn=ecs_task_execution_role.arn,
        infrastructure_role_arn=ecs_infrastructure_role.arn,
        task_role_arn=ecs_task_role.arn,
        primary_container=ExpressGatewayServicePrimaryContainerArgs(
            image=repo.repository_url.apply(lambda url: f"{url}:latest"),
            container_port=8080,
            environments=[
                ExpressGatewayServicePrimaryContainerEnvironmentArgs(
                    name="BUCKET_NAME", value=bucket.bucket
                ),
            ],
            secrets=[
                ExpressGatewayServicePrimaryContainerSecretArgs(
                    name="VESPA_ENDPOINT", value_from=vespa_endpoint.arn
                ),
                ExpressGatewayServicePrimaryContainerSecretArgs(
                    name="VESPA_READ_TOKEN", value_from=vespa_read_token.arn
                ),
            ],
        ),
        health_check_path="/",
        cpu="1024",
        memory="2048",
        scaling_targets=[
            ExpressGatewayServiceScalingTargetArgs(
                auto_scaling_metric="AVERAGE_CPU",
                auto_scaling_target_value=70,
                min_task_count=1,
                max_task_count=4,
            ),
        ],
    )
    pulumi.export(
        "ecs_express_service_url",
        ecs_express_service.ingress_paths.apply(
            lambda paths: paths[0].endpoint if paths else None
        ),
    )

    # region Prefect
    ecr_repository = components_aws.ecr.Repository(
        name=f"{name}-prefect-ecr-repository",
        aws_ecr_repository_args=ecr.RepositoryArgs(
            name=f"{name}-prefect",
            encryption_configurations=[
                ecr.RepositoryEncryptionConfigurationArgs(
                    encryption_type="AES256",
                )
            ],
            image_scanning_configuration=ecr.RepositoryImageScanningConfigurationArgs(
                scan_on_push=False,
            ),
            image_tag_mutability="MUTABLE",
        ),
    )

    # endregion

    # region vespa-feeder

    vespa_feeder_ecr_repo = ecr.Repository(
        f"{name}-vespa-feeder-repo",
        name=f"{name}-vespa-feeder",
        encryption_configurations=[
            ecr.RepositoryEncryptionConfigurationArgs(
                encryption_type="AES256",
            )
        ],
        image_scanning_configuration=ecr.RepositoryImageScanningConfigurationArgs(
            scan_on_push=False,
        ),
        image_tag_mutability="MUTABLE",
    )

    vespa_feeder_ecr_lifecycle = ecr.LifecyclePolicy(
        f"{name}-vespa-feeder-ecr-lifecycle-policy",
        repository=vespa_feeder_ecr_repo.name,
        policy=json.dumps(
            {
                "rules": [
                    {
                        "rulePriority": 1,
                        "description": "Keep last 50 images",
                        "selection": {
                            "tagStatus": "any",
                            "countType": "imageCountMoreThan",
                            "countNumber": 50,
                        },
                        "action": {"type": "expire"},
                    }
                ]
            }
        ),
    )

    # endregion
