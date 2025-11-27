"""AWS infrastructure for the Search API using Pulumi."""

import json

import pulumi
import pulumi_docker as docker
from pulumi_aws import cloudwatch, ec2, ecr, ecs, iam, lb, s3

from search.config import AWS_REGION, GIT_COMMIT_HASH, REPO_ROOT_DIR

bucket = s3.Bucket("search")

application_name = "search-api"
dockerfile_path = REPO_ROOT_DIR / "api" / "Dockerfile"

# Create a private ECR repository to store the Docker image
repo = ecr.Repository(
    f"{application_name}-repo",
    image_scanning_configuration=ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    image_tag_mutability="MUTABLE",
)

# Get authorization token for ECR
auth = ecr.get_authorization_token()

# Build and publish the image to the ECR repository
image = docker.Image(
    f"{application_name}-image",
    build=docker.DockerBuildArgs(
        context=str(REPO_ROOT_DIR),
        dockerfile=str(dockerfile_path),
        platform="linux/amd64",  # Specify platform
    ),
    image_name=pulumi.Output.concat(repo.repository_url, ":", GIT_COMMIT_HASH),
    registry=docker.RegistryArgs(
        server=auth.proxy_endpoint,
        username=auth.user_name,
        password=auth.password,
    ),
)

# Create an ECS cluster to run the service
cluster = ecs.Cluster(f"{application_name}-cluster")

# Get the default VPC and subnets to deploy into
default_vpc = ec2.get_vpc(default=True)
default_subnet_ids = ec2.get_subnets(
    filters=[ec2.GetSubnetsFilterArgs(name="vpc-id", values=[default_vpc.id])]
).ids

# Create a security group that allows HTTP ingress and all egress
sg = ec2.SecurityGroup(
    f"{application_name}-security-group",
    vpc_id=default_vpc.id,
    description="Allow HTTP ingress for Search API",
    ingress=[
        ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=80,
            to_port=80,
            cidr_blocks=["0.0.0.0/0"],
        ),
        ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8000,
            to_port=8000,
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
    egress=[
        ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
)

# Create a load balancer to listen for HTTP traffic
alb = lb.LoadBalancer(
    f"{application_name}-alb",
    internal=False,
    security_groups=[sg.id],
    subnets=default_subnet_ids,
)

target_group = lb.TargetGroup(
    f"{application_name}-tg",
    port=8000,
    protocol="HTTP",
    target_type="ip",
    vpc_id=default_vpc.id,
    health_check=lb.TargetGroupHealthCheckArgs(
        enabled=True,
        healthy_threshold=2,
        unhealthy_threshold=3,
        timeout=10,
        interval=30,
        path="/",
        matcher="200",
        protocol="HTTP",
        port="traffic-port",
    ),
)

listener = lb.Listener(
    f"{application_name}-listener",
    load_balancer_arn=alb.arn,
    port=80,
    default_actions=[
        lb.ListenerDefaultActionArgs(
            type="forward",
            target_group_arn=target_group.arn,
        )
    ],
)

# Create an IAM role for the ECS task execution
ecs_task_execution_role = iam.Role(
    f"{application_name}-ecs-task-exec-role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                }
            ],
        }
    ),
)

iam.RolePolicyAttachment(
    f"{application_name}-ecs-exec-policy",
    role=ecs_task_execution_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
)

# Create an IAM role for the ECS task (used by the application running in the container)
ecs_task_role = iam.Role(
    f"{application_name}-ecs-task-role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                }
            ],
        }
    ),
)

# Add S3 read permissions for the task role
s3_policy = iam.Policy(
    f"{application_name}-s3-policy",
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

iam.RolePolicyAttachment(
    f"{application_name}-s3-policy-attachment",
    role=ecs_task_role.name,
    policy_arn=s3_policy.arn,
)

# Create a CloudWatch log group for the application logs
log_group = cloudwatch.LogGroup(
    f"{application_name}-logs",
    retention_in_days=14,
)

# Create a Fargate task definition
task_definition = ecs.TaskDefinition(
    f"{application_name}-task",
    family=f"{application_name}-task-family",
    cpu="1024",
    memory="4096",
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=ecs_task_execution_role.arn,
    task_role_arn=ecs_task_role.arn,
    container_definitions=pulumi.Output.all(
        image.image_name,
        log_group.name,
        bucket.id,
    ).apply(
        lambda args: json.dumps(
            [
                {
                    "name": f"{application_name}-container",
                    "image": args[0],
                    "portMappings": [
                        {"containerPort": 8000, "hostPort": 8000, "protocol": "tcp"}
                    ],
                    "environment": [
                        {"name": "BUCKET_NAME", "value": args[2]},
                        {"name": "AWS_REGION", "value": AWS_REGION},
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": args[1],
                            "awslogs-region": AWS_REGION,
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                    "healthCheck": {
                        "command": [
                            "CMD-SHELL",
                            "curl -f http://localhost:8000/ || exit 1",
                        ],
                        "interval": 30,
                        "timeout": 5,
                        "retries": 3,
                        "startPeriod": 60,
                    },
                }
            ]
        )
    ),
)

# Create a Fargate service to run the task definition
service = ecs.Service(
    f"{application_name}-service",
    cluster=cluster.arn,
    desired_count=1,
    launch_type="FARGATE",
    task_definition=task_definition.arn,
    network_configuration=ecs.ServiceNetworkConfigurationArgs(
        assign_public_ip=True,
        subnets=default_subnet_ids,
        security_groups=[sg.id],
    ),
    load_balancers=[
        ecs.ServiceLoadBalancerArgs(
            target_group_arn=target_group.arn,
            container_name=f"{application_name}-container",
            container_port=8000,
        )
    ],
    opts=pulumi.ResourceOptions(depends_on=[listener]),
)

# Export useful outputs
pulumi.export("bucket_name", bucket.id)
pulumi.export("log_group_name", log_group.name)
pulumi.export("api_endpoint", pulumi.Output.concat("http://", alb.dns_name))
