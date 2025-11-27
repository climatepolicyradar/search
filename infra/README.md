# Infrastructure

Pulumi stack for deploying the Search API to AWS using ECS Fargate.

## Prerequisites

- Project dependencies installed by running `just install` from the project root.
- AWS account and [credentials configured for Pulumi](https://www.pulumi.com/docs/clouds/aws/get-started/begin/). Run `aws sso login --profile labs` to authenticate.
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running locally.

## Architecture

The pulumi stack in `__main__.py` will create the following resources:

- **ECR Repository**: Private container registry for the Docker image
- **ECS Cluster**: Fargate cluster to run the containerized API
- **ECS Service**: Manages the running tasks with desired count
- **Application Load Balancer**: Routes HTTP traffic to the containers
- **Security Group**: Controls network access (HTTP on port 80)
- **CloudWatch Log Group**: Centralized logging with 14-day retention
- **IAM Roles**: Task execution role with necessary permissions

## Deployment

### Deploy the infrastructure

Deploy the infrastructure:

```bash
cd infra
uv run pulumi up --stack labs
```

Pulumi will build the Docker image, push it to a private ECR repository, and deploy the service to ECS Fargate. The output will include the public URL of the load balancer.

**Note for MacBook (ARM-based) users:** The Docker image is built for the `linux/amd64` platform to ensure compatibility with AWS Fargate. Docker Desktop handles this cross-platform build automatically.

### Destroy the infrastructure

To tear down all the created AWS resources:

```bash
uv run pulumi destroy --stack labs
```

## Getting environment variables out of the Pulumi stack

The most useful outputs are probably the S3 bucket name and the CloudWatch log group name. To get these out of the Pulumi stack, run:

```bash
cd infra
pulumi stack output bucket_name
pulumi stack output log_group_name
```

This will output the bucket name, which you can then use to set the `BUCKET_NAME` environment variable in your local environment:

```bash
export BUCKET_NAME=$(cd infra && pulumi stack output bucket_name)
```

## Viewing logs

To view the application logs in CloudWatch:

```bash
# Get the log group name
LOG_GROUP=$(pulumi stack output log_group_name)

# View recent logs using AWS CLI
aws logs tail $LOG_GROUP --follow
```
