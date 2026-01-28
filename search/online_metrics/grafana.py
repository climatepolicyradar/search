"""Helpers for interacting with Grafana"""

from datetime import date, datetime

import requests

from search.config import (
    GRAFANA_LABELS,
    get_from_env_with_fallback,
)
from search.log import get_logger
from search.online_metrics import OnlineMetricResult, PercentileResult
from search.online_metrics.date_utils import DateRange

logger = get_logger(__name__)


class GrafanaSession:
    """Session for querying Grafana data."""

    def __init__(self) -> None:
        self.api_key = get_from_env_with_fallback(
            var_name="GRAFANA_API_KEY", ssm_name="/Grafana/MetricUserApiToken"
        )
        self.url = get_from_env_with_fallback(
            var_name="GRAFANA_URL", ssm_name="/Grafana/MetricQueryURL"
        )
        self.user_id = get_from_env_with_fallback(
            var_name="GRAFANA_USER_ID", ssm_name="/Grafana/MetricUserId"
        )

    def execute_query(self, query: str, start_time: datetime, end_time: datetime):
        """Execute a Grafana query and return raw results"""
        response = requests.get(
            f"{self.url}/api/v1/query_range",
            params={
                "query": query,
                "start": start_time.isoformat() + "Z",
                "end": end_time.isoformat() + "Z",
                "step": "1h",
            },
            auth=(self.user_id, self.api_key),
        )
        data = response.json()
        if data["status"] == "success" and data["data"]["result"]:
            values = data["data"]["result"][0]["values"]
            return values
        else:
            raise ValueError(f"Grafana query returned no results: {data}")

    def get_search_latency_ms(self, date_range: DateRange) -> OnlineMetricResult:
        """
        Get the mean search API latency (p50, p95, p99) in milliseconds for the given date range (inclusive)

        :param date_range: DateRange object specifying the inclusive date range
        :return: dict with keys "p50", "p95", "p99" and values as Latency objects
        """
        start_time = date_range.get_start_time_of_day()
        end_time = date_range.get_end_time_of_day()

        # P50 (median) latency
        query_p50 = f"""histogram_quantile(0.50, sum(rate(traces_spanmetrics_latency_bucket{{{GRAFANA_LABELS}}}[5m])) by (le,job))"""

        # P95 latency
        query_p95 = f"""histogram_quantile(0.95, sum(rate(traces_spanmetrics_latency_bucket{{{GRAFANA_LABELS}}}[5m])) by (le,job))"""

        # P99 latency
        query_p99 = f"""histogram_quantile(0.99, sum(rate(traces_spanmetrics_latency_bucket{{{GRAFANA_LABELS}}}[5m])) by (le,job))"""

        results = {}
        for name, query in [("p50", query_p50), ("p95", query_p95), ("p99", query_p99)]:
            values = self.execute_query(query, start_time, end_time)
            # Get the last value in the range (latency is in seconds) and convert to milliseconds
            results[name] = float(values[-1][1]) * 1000
        return OnlineMetricResult(
            metric="search_latency_ms",
            query=f"p50: {query_p50}\np95: {query_p95}\np99: {query_p99}",
            value=PercentileResult(
                p50=results["p50"], p95=results["p95"], p99=results["p99"]
            ),
            date_range=date_range,
        )


session = GrafanaSession()
result = session.get_search_latency_ms(
    date_range=DateRange(date_from=date(2025, 12, 16), date_to=date(2025, 12, 31))
)
print(result)
