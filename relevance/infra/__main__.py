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

message_template = alerting.MessageTemplate(
    resource_name="relevance",
    opts=grafana_opts,
    name="relevance",
    template=(
        '{{ define "relevance.title" }}'
        "Relevance {{ .CommonLabels.alertname }}: {{ len .Alerts.Firing }} firing"
        "{{ end }}\n"
        '{{ define "relevance.text" }}'
        "{{ range .Alerts.Firing }}"
        "• {{ .Annotations.summary }}\n"
        "{{ end }}"
        "{{ end }}"
    ),
)

contact_point = alerting.ContactPoint(
    resource_name="relevance",
    opts=grafana_opts,
    name="relevance",
    slacks=[
        alerting.ContactPointSlackArgs(
            url=config.require_secret("slack_webhook_url"),
            title=pulumi.Output.concat('{{ template "', message_template.name, '.title" . }}'),
            text=pulumi.Output.concat('{{ template "', message_template.name, '.text" . }}'),
            icon_emoji=":chart_with_downwards_trend:",
            disable_resolve_message=True,
            username="Relevance tests",
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
            no_data_state="NoData",
            annotations={
                "summary": (
                    "{{ if $labels.suite }}"
                    '{{ $labels.suite }} {{ $labels.metric }} dropped by {{ printf "%.3f" $values.score_drop.Value }}'
                    "{{ else }}"
                    "No relevance scores from main in the last day"
                    "{{ end }}"
                ),
                "description": "Latest run is that far below the previous 7-day average.",
            },
            notification_settings=alerting.RuleGroupRuleNotificationSettingsArgs(
                contact_point=contact_point.name,
                repeat_interval="24h",
            ),
            datas=[
                alerting.RuleGroupRuleDataArgs(
                    ref_id="score_drop",
                    datasource_uid=prometheus.uid,
                    relative_time_range=alerting.RuleGroupRuleDataRelativeTimeRangeArgs(
                        from_=600,
                        to=0,
                    ),
                    model=json.dumps(
                        {
                            "refId": "score_drop",
                            "instant": True,
                            "expr": (
                                'max by (suite, metric) (avg_over_time(relevance_score_ratio{branch="main"}[7d] offset 1d)) - '
                                'max by (suite, metric) (last_over_time(relevance_score_ratio{branch="main"}[1d]))'
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
                            "expression": "score_drop",
                            "conditions": [{"evaluator": {"type": "gt", "params": [0.02]}}],
                        }
                    ),
                ),
            ],
        ),
        alerting.RuleGroupRuleArgs(
            name="run-errors",
            condition="has_errors",
            no_data_state="OK",
            annotations={
                "summary": "{{ $labels.suite }} had {{ $values.errors.Value }} erroring case(s)",
                "description": "Cases that errored are left out of the score averages.",
            },
            notification_settings=alerting.RuleGroupRuleNotificationSettingsArgs(
                contact_point=contact_point.name,
                repeat_interval="24h",
            ),
            datas=[
                alerting.RuleGroupRuleDataArgs(
                    ref_id="errors",
                    datasource_uid=prometheus.uid,
                    relative_time_range=alerting.RuleGroupRuleDataRelativeTimeRangeArgs(
                        from_=600,
                        to=0,
                    ),
                    model=json.dumps(
                        {
                            "refId": "errors",
                            "instant": True,
                            "expr": 'max by (suite) (last_over_time(relevance_errors_total{branch="main"}[1d]))',
                        }
                    ),
                ),
                alerting.RuleGroupRuleDataArgs(
                    ref_id="has_errors",
                    datasource_uid="__expr__",
                    relative_time_range=alerting.RuleGroupRuleDataRelativeTimeRangeArgs(
                        from_=0,
                        to=0,
                    ),
                    model=json.dumps(
                        {
                            "type": "threshold",
                            "refId": "has_errors",
                            "expression": "errors",
                            "conditions": [{"evaluator": {"type": "gt", "params": [0]}}],
                        }
                    ),
                ),
            ],
        ),
    ],
)
