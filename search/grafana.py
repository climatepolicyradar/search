"""Helpers for interacting with Grafana"""

from datetime import datetime

import requests
from pydantic import NonNegativeFloat

from search.config import (
    GRAFANA_LABELS,
    get_from_env_with_fallback,
)
from search.date_utils import check_date_range
from search.log import get_logger

logger = get_logger(__name__)


class Latency(NonNegativeFloat):
    """A latency value in milliseconds returned from Grafana"""


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

    def get_search_latency(self, start_date: str, end_date: str) -> dict[str, Latency]:
        """
        Get the mean search API latency (p50, p95, p99) in milliseconds for the given date range (inclusive)

        :param start_date: start of date range in YYYY-MM-DD format (inclusive)
        :param end_date: end of date range in YYYY-MM-DD format (inclusive)
        :return: dict with keys "p50", "p95", "p99" and values as Latency objects
        """
        date_range = check_date_range(start_date, end_date)
        start_time = datetime.combine(date_range.date_from, datetime.min.time())
        end_time = datetime.combine(date_range.date_to, datetime.max.time())

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
        return {name: Latency(value) for name, value in results.items()}
