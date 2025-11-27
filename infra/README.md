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
- **IAM Roles**: Task execution role and task role with S3 and CloudWatch permissions

## Deployment

### Deploy the infrastructure

Deploy the infrastructure:

```bash
cd infra && pulumi up
```

Pulumi will build the Docker image, push it to a private ECR repository, and deploy the service to ECS Fargate. The output will include the public URL of the load balancer.

**Note for MacBook (ARM-based) users:** The Docker image is built for the `linux/amd64` platform to ensure compatibility with AWS Fargate. Docker Desktop handles this cross-platform build automatically.

### Force a new deployment (refresh ECS service)

If you've made code changes and want to force a new deployment without changing infrastructure, you can update the ECS service to pull a new task definition:

```bash
# Method 1: Force new task definition revision by updating service
aws ecs update-service \
  --cluster $(cd infra && pulumi stack output cluster_name) \
  --service $(cd infra && pulumi stack output service_name) \
  --force-new-deployment \
  --profile labs
```

The first method is faster for code changes (just restarts tasks with new code), while the second method rebuilds the Docker image and is useful when dependencies change or you want a full stack refresh.

### Destroy the infrastructure

To tear down all the created AWS resources:

```bash
cd infra && pulumi destroy
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
aws logs tail $(cd infra && pulumi stack output log_group_name) --follow --profile labs
```
