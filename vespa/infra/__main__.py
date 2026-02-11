import pulumi
import pulumi_aws as aws

config = pulumi.Config()

instance_type = "t3.large"
app_name = "search-vespa"

# region EC2
default_vpc = aws.ec2.get_vpc(default=True)
default_subnets = aws.ec2.get_subnets(
    filters=[{"name": "vpc-id", "values": [default_vpc.id]}]
)

lb_security_group = aws.ec2.SecurityGroup(
    f"{app_name}-lb-sg",
    name=f"{app_name}-lb-sg",
    vpc_id=default_vpc.id,
    ingress=[
        {
            "protocol": "tcp",
            "from_port": 8080,
            "to_port": 8080,
            "cidr_blocks": [default_vpc.cidr_block],
            "description": "Query API access",
        },
        {
            "protocol": "tcp",
            "from_port": 19071,
            "to_port": 19071,
            "cidr_blocks": [default_vpc.cidr_block],
            "description": "Config server access",
        },
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]},
    ],
)

instance_role = aws.iam.Role(
    f"{app_name}-instance-role",
    name=f"{app_name}-instance-role",
    assume_role_policy="""{
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Effect": "Allow"
        }]
    }""",
)


aws.iam.RolePolicyAttachment(
    f"{app_name}-ssm-policy",
    role=instance_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)

instance_profile = aws.iam.InstanceProfile(
    f"{app_name}-instance-profile",
    name=f"{app_name}-instance-profile",
    role=instance_role.name,
)

security_group = aws.ec2.SecurityGroup(
    f"{app_name}-sg",
    name=f"{app_name}-sg",
    vpc_id=default_vpc.id,
    description="Vespa dev instance",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8080,
            to_port=8080,
            security_groups=[lb_security_group.id],
            description="Query API from LoadBalancer",
        ),
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=19071,
            to_port=19071,
            security_groups=[lb_security_group.id],
            description="Config server from LoadBalancer",
        ),
    ],
    egress=[
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]},
    ],
)

ami = aws.ec2.get_ami(
    most_recent=True,
    owners=["amazon"],
    filters=[
        {"name": "name", "values": ["al2023-ami-2023.*-x86_64"]},
        {"name": "virtualization-type", "values": ["hvm"]},
    ],
)

user_data = """#!/bin/bash
set -e

yum update -y
yum install -y docker git
systemctl enable docker
systemctl start docker

docker pull vespaengine/vespa
docker rm -f vespa || true
docker run -d --name vespa -p 8080:8080 -p 19071:19071 \
  --hostname search-vespa \
  -e VESPA_CONFIGSERVERS=search-vespa \
  vespaengine/vespa

echo "Vespa instance ready"
"""

instance = aws.ec2.Instance(
    f"{app_name}-instance",
    instance_type=instance_type,
    ami=ami.id,
    subnet_id=default_subnets.ids[0],
    vpc_security_group_ids=[security_group.id],
    iam_instance_profile=instance_profile.name,
    associate_public_ip_address=True,
    root_block_device={
        "volume_size": 50,
        "volume_type": "gp3",
    },
    user_data=user_data,
    tags={"Name": f"{app_name}-instance"},
)

eip = aws.ec2.Eip(f"{app_name}-eip", instance=instance.id)

lb = aws.lb.LoadBalancer(
    f"{app_name}-lb",
    name=f"{app_name}-lb",
    internal=True,
    load_balancer_type="application",
    security_groups=[lb_security_group.id],
    subnets=default_subnets.ids,
)

target_group = aws.lb.TargetGroup(
    f"{app_name}-tg",
    name=f"{app_name}-tg",
    port=8080,
    protocol="HTTP",
    target_type="instance",
    vpc_id=default_vpc.id,
    health_check={
        "path": "/",
        "matcher": "200",
    },
)

target_group_attachment = aws.lb.TargetGroupAttachment(
    f"{app_name}-tg-attachment",
    target_group_arn=target_group.arn,
    target_id=instance.id,
    port=8080,
)

listener = aws.lb.Listener(
    f"{app_name}-listener",
    load_balancer_arn=lb.arn,
    port=8080,
    protocol="HTTP",
    default_actions=[
        {
            "type": "forward",
            "target_group_arn": target_group.arn,
        }
    ],
)

# Config server (port 19071) for deployments
config_target_group = aws.lb.TargetGroup(
    f"{app_name}-config-tg",
    name=f"{app_name}-config-tg",
    port=19071,
    protocol="HTTP",
    target_type="instance",
    vpc_id=default_vpc.id,
    health_check={
        "path": "/state/v1/health",
        "matcher": "200",
    },
)

config_target_group_attachment = aws.lb.TargetGroupAttachment(
    f"{app_name}-config-tg-attachment",
    target_group_arn=config_target_group.arn,
    target_id=instance.id,
    port=19071,
)

config_listener = aws.lb.Listener(
    f"{app_name}-config-listener",
    load_balancer_arn=lb.arn,
    port=19071,
    protocol="HTTP",
    default_actions=[
        {
            "type": "forward",
            "target_group_arn": config_target_group.arn,
        }
    ],
)

vpc_link = aws.apigatewayv2.VpcLink(
    f"{app_name}-vpc-link",
    name=f"{app_name}-vpc-link",
    security_group_ids=[lb_security_group.id],
    subnet_ids=default_subnets.ids,
)
# endregion

# region gateway
api = aws.apigatewayv2.Api(
    f"{app_name}-api",
    name=f"{app_name}-api",
    protocol_type="HTTP",
)

# region Gateway
public_search_integration = aws.apigatewayv2.Integration(
    f"{app_name}-search-integration",
    api_id=api.id,
    integration_type="HTTP_PROXY",
    integration_method="ANY",
    integration_uri=listener.arn,
    connection_type="VPC_LINK",
    connection_id=vpc_link.id,
    request_parameters={
        "overwrite:path": "/search",
    },
)

search_route = aws.apigatewayv2.Route(
    f"{app_name}-search",
    api_id=api.id,
    route_key="ANY /search",
    target=public_search_integration.id.apply(lambda id: f"integrations/{id}"),
    authorization_type="NONE",
)

# Protected - IAM auth (uses your existing SSO)
protected_integration = aws.apigatewayv2.Integration(
    f"{app_name}-protected-integration",
    api_id=api.id,
    integration_type="HTTP_PROXY",
    integration_method="ANY",
    integration_uri=listener.arn,
    connection_type="VPC_LINK",
    connection_id=vpc_link.id,
    request_parameters={
        "overwrite:path": "/$request.path.proxy",
    },
)

protected_route = aws.apigatewayv2.Route(
    f"{app_name}-protected",
    api_id=api.id,
    route_key="ANY /{proxy+}",
    target=protected_integration.id.apply(lambda id: f"integrations/{id}"),
    authorization_type="AWS_IAM",
)

# Config server integrations (port 19071) - need separate integrations to preserve path prefixes
application_integration = aws.apigatewayv2.Integration(
    f"{app_name}-application-integration",
    api_id=api.id,
    integration_type="HTTP_PROXY",
    integration_method="ANY",
    integration_uri=config_listener.arn,
    connection_type="VPC_LINK",
    connection_id=vpc_link.id,
    request_parameters={
        "overwrite:path": "/application/$request.path.proxy",
    },
)

application_route = aws.apigatewayv2.Route(
    f"{app_name}-application",
    api_id=api.id,
    route_key="ANY /application/{proxy+}",
    target=application_integration.id.apply(lambda id: f"integrations/{id}"),
    authorization_type="AWS_IAM",
)

state_integration = aws.apigatewayv2.Integration(
    f"{app_name}-state-integration",
    api_id=api.id,
    integration_type="HTTP_PROXY",
    integration_method="ANY",
    integration_uri=config_listener.arn,
    connection_type="VPC_LINK",
    connection_id=vpc_link.id,
    request_parameters={
        "overwrite:path": "/state/$request.path.proxy",
    },
)

state_route = aws.apigatewayv2.Route(
    f"{app_name}-state",
    api_id=api.id,
    route_key="ANY /state/{proxy+}",
    target=state_integration.id.apply(lambda id: f"integrations/{id}"),
    authorization_type="AWS_IAM",
)

# Separate integration for status.html (no {proxy+} to capture)
status_integration = aws.apigatewayv2.Integration(
    f"{app_name}-status-integration",
    api_id=api.id,
    integration_type="HTTP_PROXY",
    integration_method="GET",
    integration_uri=config_listener.arn,
    connection_type="VPC_LINK",
    connection_id=vpc_link.id,
    request_parameters={
        "overwrite:path": "/status.html",
    },
)

status_route = aws.apigatewayv2.Route(
    f"{app_name}-status",
    api_id=api.id,
    route_key="GET /status.html",
    target=status_integration.id.apply(lambda id: f"integrations/{id}"),
    authorization_type="AWS_IAM",
)

production_stage = aws.apigatewayv2.Stage(
    f"{app_name}-production",
    api_id=api.id,
    name="production",
    auto_deploy=True,
)
# endregion


pulumi.export("instance_id", instance.id)
pulumi.export("public_ip", eip.public_ip)
pulumi.export(
    "ssm_command", instance.id.apply(lambda id: f"aws ssm start-session --target {id}")
)
pulumi.export("vespa_url", eip.public_ip.apply(lambda ip: f"http://{ip}:8080"))

# This is part of the public API - edit with caution
pulumi.export("apigateway_production_stage_invoke_url", production_stage.invoke_url)
# endregion
