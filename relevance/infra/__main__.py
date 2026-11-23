import json

import pulumi
from pulumiverse_grafana import alerting, oss
from pulumiverse_grafana.provider import Provider

config = pulumi.Config()

grafana = Provider(
    resource_name="grafana",
    url=config.require_secret("grafana_url"),
    auth=config.require_secret("grafana_auth"),
)

grafana_opts = pulumi.ResourceOptions(
    provider=grafana,
)

prometheus = oss.get_data_source_output(
    name=config.require_secret("prometheus_data_source_name"),
    opts=pulumi.InvokeOutputOptions(provider=grafana),
)

folder = oss.Folder(
    resource_name="relevance",
    title="Search API Relevance",
    opts=grafana_opts,
)

contact_point = alerting.ContactPoint(
    resource_name="relevance",
    opts=grafana_opts,
    name="relevance",
    slacks=[
        alerting.ContactPointSlackArgs(
            url=config.require_secret("slack_webhook_url"),
        ),
    ],
)

alerting.RuleGroup(
    name="relevance",
    opts=grafana_opts,
    resource_name="relevance-alerts",
    folder_uid=folder.uid,
    interval_seconds=3600,
    rules=[
        alerting.RuleGroupRuleArgs(
            name="metric-degradation",
            condition="drop_too_large",
            notification_settings=alerting.RuleGroupRuleNotificationSettingsArgs(
                contact_point=contact_point.name,
            ),
            datas=[
                alerting.RuleGroupRuleDataArgs(
                    ref_id="pass_rate_drop",
                    datasource_uid=prometheus.uid,
                    relative_time_range=alerting.RuleGroupRuleDataRelativeTimeRangeArgs(
                        from_=600,
                        to=0,
                    ),
                    model=json.dumps(
                        {
                            "refId": "pass_rate_drop",
                            "instant": True,
                            "expr": (
                                'max by (suite) (avg_over_time(relevance_score_ratio{metric="pass_rate"}[7d] offset 1d)) - '
                                'max by (suite) (last_over_time(relevance_score_ratio{metric="pass_rate"}[1d]))'
                            ),
                        }
                    ),
                ),
                alerting.RuleGroupRuleDataArgs(
                    ref_id="drop_too_large",
                    datasource_uid="__expr__",
                    relative_time_range=alerting.RuleGroupRuleDataRelativeTimeRangeArgs(
                        from_=0,
                        to=0,
                    ),
                    model=json.dumps(
                        {
                            "type": "threshold",
                            "refId": "drop_too_large",
                            "expression": "pass_rate_drop",
                            "conditions": [{"evaluator": {"type": "gt", "params": [0.02]}}],
                        }
                    ),
                ),
            ],
        ),
    ],
)
