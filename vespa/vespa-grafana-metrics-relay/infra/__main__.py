import json

import pulumi
import pulumi_aws as aws
from pulumi import Config

pulumi_config = Config()

VESPA_PUBLIC_CERT = pulumi_config.require("VESPA_PUBLIC_CERT")
VESPA_PRIVATE_KEY = pulumi_config.require("VESPA_PRIVATE_KEY")
VESPA_ENDPOINT = pulumi_config.require("VESPA_ENDPOINT")
AWS_REGION = pulumi_config.require("AWS_REGION")
lambda_runtime = pulumi_config.require("lambda_runtime")
project = pulumi_config.require("project")
cloudwatch_namespace = pulumi_config.require("cloudwatch_namespace")
metric_collection_rate = pulumi_config.require("metric_collection_rate")
lambda_timeout_seconds = pulumi_config.require("lambda_timeout_seconds")


ssm_parameter_vespa_public_cert = aws.ssm.Parameter(
    "VESPA_PUBLIC_CERT",
    name="VESPA_PUBLIC_CERT",
    type="SecureString",
    value=str(VESPA_PUBLIC_CERT),
    overwrite=True,
)
pulumi.export("ssm_parameter_vespa_public_cert", ssm_parameter_vespa_public_cert.arn)


ssm_parameter_vespa_private_key = aws.ssm.Parameter(
    "VESPA_PRIVATE_KEY",
    name="VESPA_PRIVATE_KEY",
    type="SecureString",
    value=str(VESPA_PRIVATE_KEY),
    overwrite=True,
)
pulumi.export("ssm_parameter_vespa_private_key", ssm_parameter_vespa_private_key.arn)

lambda_role = aws.iam.Role(
    f"lambda_role-{project}",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
)
pulumi.export("lambda_role", lambda_role.arn)

lambda_role_policy = aws.iam.RolePolicy(
    f"lambda_role_policy-{project}",
    role=lambda_role.name,
    policy=pulumi.Output.all(
        ssm_parameter_vespa_public_cert=ssm_parameter_vespa_public_cert.arn,
        ssm_parameter_vespa_private_key=ssm_parameter_vespa_private_key.arn,
    ).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "cloudwatch:PutMetricData",
                        "Resource": "*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["ssm:GetParameters"],
                        "Resource": [
                            args["ssm_parameter_vespa_private_key"],
                            args["ssm_parameter_vespa_public_cert"],
                        ],
                    },
                ],
            }
        )
    ),
)
pulumi.export("lambda_role_policy_name", lambda_role_policy.name)


lambda_function = aws.lambda_.Function(
    f"lambda-function-{project}",
    role=lambda_role.arn,
    runtime=lambda_runtime,
    handler="vespa_cloudwatch_emitter.lambda_handler",
    code=pulumi.AssetArchive({".": pulumi.FileArchive("./lambda_code/")}),
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "CERT_NAME": "VESPA_PUBLIC_CERT",
            "KEY_NAME": "VESPA_PRIVATE_KEY",
            "SSM_REGION": AWS_REGION,
            "VESPA_ENDPOINT": VESPA_ENDPOINT,
            "CLOUDWATCH_NAMESPACE": cloudwatch_namespace,
            "CONSUMER": "vespa",
        },
    ),
    timeout=int(lambda_timeout_seconds),
)
pulumi.export("lambda_function_arn", lambda_function.arn)


rule = aws.cloudwatch.EventRule(
    f"event-rule-{project}",
    description="Schedule to declare the schedule of metric collection",
    schedule_expression=metric_collection_rate,
)
pulumi.export("event_rule_arn", rule.arn)


target = aws.cloudwatch.EventTarget(
    f"event-target-{project}", rule=rule.name, arn=lambda_function.arn
)
pulumi.export("event_target_arn", target.arn)


lambda_permission = aws.lambda_.Permission(
    f"lambda-permission-{project}",
    action="lambda:InvokeFunction",
    function=lambda_function.arn,
    principal="events.amazonaws.com",
    source_arn=rule.arn,
)
pulumi.export("lambda_permission", lambda_permission.id)
