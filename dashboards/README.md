# Grafana Dashboard

`dashboards/vespa-search.json` is a Grafana dashboard for the `search` Vespa
instance. It uses the CloudWatch data source (Grafana JSON model v2) and can be
imported via **Dashboards → Import** in Grafana Cloud.

NOTE: that this isn't set to sync with Grafana yet. That will be done in a
separate PR.

## About

Metrics are sourced from the `vespa` CloudWatch namespace via the
[`search_vespa_metrics`](../../navigator-infra/vespa/metrics_infra/) Lambda
stack. On import, select the CloudWatch data source when prompted by the
`datasource` template variable.

The dashboard filters on
`applicationId = climate-policy-radar.search.search-production`. Edit panel
dimensions to point at a different Vespa instance if needed.

## Panels

- **Document counts** — `documents`, `passages`, and `labels` schema totals over
  time.
- **Query & feed** — query rate and feed commit operations rate.
- **Query latency** — P95, P99, and mean (ms), with a 2 s threshold line.
- **HTTP status** — 2xx / 4xx / 5xx response counts.
- **Resources** — CPU, proton disk usage (bytes), disk utilisation (%), and
  memory utilisation (%).
