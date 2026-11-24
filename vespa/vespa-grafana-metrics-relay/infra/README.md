# Metrics Infra

This directory contains infrastructure to support the retrieval of metrics from Vespa. Metrics are pushed to CloudWatch and can be visualised in Grafana.

## Architecture

We could store private key pairs in Grafana to poll Vespa. This was deemed sub-optimal as Vespa doesn't provide granular access. Therefore we've gone for the solution of pulling metrics from Vespa into CloudWatch.

- [Pulling Metrics from Vespa](https://docs.vespa.ai/en/operations-selfhosted/monitoring.html#pulling-metrics-from-vespa).
- [Lambda Deployment Flow](https://github.com/vespa-engine/metrics-emitter/tree/master/cloudwatch)

---

We've taken this and pulumi-ified it into a pulumi stack.

- Private key pair stored in SSM Parameter Store (SecureString).
- Lambda instance that polls Vespa on the `/metrics/v2` endpoint every 5 minutes.
  - The metrics endpoint was chosen over the `prometheus` endpoint as it outputs as JSON.
- Pushes metrics to CloudWatch under a configurable namespace (default: `vespa`).
- Grafana pulls metrics from CloudWatch using a role with minimal IAM credentials.
- Grafana dashboard taken from the Vespa quickstart tutorial — [Grafana Detailed Monitoring Dashboard](https://docs.vespa.ai/en/operations-selfhosted/monitoring.html#monitoring-with-grafana).
