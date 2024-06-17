# Metrics Infra

This directory contains infrastructure to support the retrieval of metrics from vespa. This is so we can load them into Grafana which is our centralised of our entire infrastructure. This also allows us to set alerts that seemlessly integrate with slack and other channels of communication.

## Architecture

We could store private key pairs in grafana to poll vespa. This was deemed sub-optimal as vespa doesn't provide granular access. Therefore we've gone for the solution of pulling metrics from cloudwatch into vespa.

- [Pulling Metrics from Vespa](https://docs.vespa.ai/en/operations-selfhosted/monitoring.html#pulling-metrics-from-vespa).
- [Lambda Deployment Flow](https://github.com/vespa-engine/metrics-emitter/tree/master/cloudwatch)
  
-----

We've taken this and pulumi-fied it into a pulumi stack.

- Private key pair stored in secrets manager.
- Lambda instance that polls vespa on the `/metrics/v2` endpoint.
  - The metrics endpoint was chosen over the `prometheus` endpoint as it outputs as json.
- Pushes metrics to cloudwatch on an interval.
- Grafana pulls metrcs from cloudwatch using a role with minimal iam credentials.
- Grafana dashboard that is taken from this template in the quickstart tutorial - [Grafana Detailed Monitoring Dashboard](https://docs.vespa.ai/en/operations-selfhosted/monitoring.html#monitoring-with-grafana).