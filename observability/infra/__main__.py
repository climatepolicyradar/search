"""
Grafana Synthetic Monitoring uptime checks for the search-api health probes.

`api/health.py` exposes one route per probe — `/search/health/probes/{probe}` — each
answering 200 when its dependency is up and 503 when it is not. This project
points one Grafana HTTP check at each of them, so every dependency carries its
own uptime series instead of being collapsed into the single `/search/health`
status. A red check then names the thing that is down.

Split into its own Pulumi project (separate from `infra/`, alongside
`k6/infra/`) so that changing a check only runs a `pulumi up` scoped to these
Grafana resources — not the full search-api stack (ECS, S3, IAM, Vespa config),
which would otherwise risk rolling in whatever else has drifted in that stack.

The probe names are not imported from `api.health`: that module pulls in
`api.settings`, which requires the Vespa endpoint and read token at import time,
and a Pulumi run has neither. `tests/api/test_health.py` fails if `PROBE_NAMES`
below and `api.health.PROBES` ever drift apart.

First deploy:

    cd observability/infra
    pulumi stack init climatepolicyradar/search-observability/production
    pulumi config set --secret grafana_sm_access_token <token>
    pulumi up
"""

from collections.abc import Sequence

import pulumi
import pulumiverse_grafana as grafana

# As defined in `./api/health.py`
HEALTH_PROBE_PATH = "/health/probes"

# One entry per key in `api.health.PROBES`, in the same order.
PROBE_NAMES = [
    "vespa",
    "documents.search",
    "documents.get",
    "labels.search",
    "passages.search",
]

# `documents.get` runs two Vespa requests back to back, each bounded by
# `search.engines.vespa_query.client.API_TIMEOUT` (5s), so the slowest healthy
# response sits right on this limit. That is deliberate: a probe that takes
# longer than its own budget allows is not a healthy dependency.
TIMEOUT_MS = 10_000


def resolve_probe_ids(available: dict[str, int], wanted: Sequence[str]) -> list[int]:
    """Map Grafana probe location names to their IDs, failing loudly on a miss."""
    missing = [name for name in wanted if name not in available]
    if missing:
        raise ValueError(
            f"Unknown Grafana probe location(s): {', '.join(missing)}. "
            f"Available: {', '.join(sorted(available))}"
        )
    return [available[name] for name in wanted]


config = pulumi.Config()
env = pulumi.get_stack()

grafana_provider = grafana.Provider(
    "grafana",
    sm_access_token=config.require_secret("grafana_sm_access_token"),
    sm_url=config.require("grafana_sm_url"),
)

api_base_url = config.require("api_base_url").rstrip("/")
probe_locations = config.require_object("grafana_probe_locations")

location_ids = grafana.syntheticmonitoring.get_probes_output(
    opts=pulumi.InvokeOptions(provider=grafana_provider)
).probes.apply(lambda probes: resolve_probe_ids(probes, probe_locations))

for probe_name in PROBE_NAMES:
    check = grafana.syntheticmonitoring.Check(
        f"search-api-check-{probe_name}",
        job=f"search-api-check-{probe_name}",
        target=f"{api_base_url}{HEALTH_PROBE_PATH}/{probe_name}",
        probes=location_ids,
        enabled=True,
        frequency=60000,  # ms
        timeout=TIMEOUT_MS,
        labels={"service": "search-api", "environment": env, "probe": probe_name},
        settings=grafana.syntheticmonitoring.CheckSettingsArgs(
            http=grafana.syntheticmonitoring.CheckSettingsHttpArgs(
                method="GET",
                # The route answers 200 only when the probe passed, so uptime is
                # the status code and nothing else needs asserting.
                valid_status_codes=[200],
                fail_if_not_ssl=True,
                # Without this a cached 200 at the edge would keep reporting a
                # dependency as up after it had gone down.
                cache_busting_query_param_name="__sm_cb",
            ),
        ),
        opts=pulumi.ResourceOptions(provider=grafana_provider),
    )

    # @see: https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/configure-alerts/configure-per-check-alerts/
    grafana.syntheticmonitoring.CheckAlerts(
        f"search-api-check-alert-{probe_name}",
        # `Check` exposes no numeric id of its own, and Pulumi's own `id` is the
        # check id as a string, which this wants as an int.
        check_id=check.id.apply(int),
        alerts=[
            grafana.syntheticmonitoring.CheckAlertsAlertArgs(
                name="ProbeFailedExecutionsTooHigh",
                threshold=5,
                period="5m",
            ),
            grafana.syntheticmonitoring.CheckAlertsAlertArgs(
                name="TLSTargetCertificateCloseToExpiring",
                threshold=14,
                # Not a windowed rule: it asks how much life the certificate has
                # left, so there is nothing to average over.
                period="",
            ),
        ],
        opts=pulumi.ResourceOptions(provider=grafana_provider),
    )
