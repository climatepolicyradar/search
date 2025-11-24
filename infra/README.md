# Infrastructure

This directory contains the infrastructure for the search project.

## Prerequisites

Make sure you have all of the dependencies installed:

```bash
just install
```

and that you're logged in to AWS:

```bash
aws sso login --profile labs
```

## Usage

To deploy the infrastructure, run:

```bash
cd infra
pulumi up
```

## Cleanup

To cleanup the infrastructure, run:

```bash
cd infra
pulumi destroy
```

# Getting environment variables out of the Pulumi stack

To get the bucket name out of the Pulumi stack, run:

```bash
cd infra
pulumi stack output bucket_name
```

This will output the bucket name, which you can then use to set the `BUCKET_NAME` environment variable in your local environment:

```bash
export BUCKET_NAME=$(cd infra && pulumi stack output bucket_name)
```

or add it to your `.env` file:

```bash
echo "BUCKET_NAME=$(cd infra && pulumi stack output bucket_name)" >> .env
```
