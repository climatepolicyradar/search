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
