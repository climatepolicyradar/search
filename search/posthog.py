"""Helpers for interacting with PostHog"""

from typing import Any

import pandas as pd
import requests

from search import config
from search.log import get_logger

logger = get_logger(__name__)


class PostHogSession:
    """Session for querying PostHog analytics data."""

    def __init__(self) -> None:
        """Initialize PostHog session class."""
        self.disable = config.DISABLE_POSTHOG

        if self.disable:
            logger.info(
                "PostHogSession has been created with connection disabled. "
                "Pass an empty or false value to env variable DISABLE_POSTHOG to enable."
            )

        self.api_key = config.POSTHOG_API_KEY
        self.host = config.POSTHOG_HOST
        self.project_id = config.POSTHOG_PROJECT_ID

    def _make_request(
        self, endpoint: str = "query/", json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated request to PostHog API."""
        if self.disable:
            logger.info(
                "PostHogSession has been created with connection disabled. Pass an empty or false value to the env variable DISABLE_POSTHOG to enable PostHog connection."
            )
            return {}

        url = f"{self.host}/api/projects/{self.project_id}/{endpoint}"
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json=json_data,
        )
        response.raise_for_status()
        return response.json()

    def execute_query(
        self,
        hogql_query: str,
    ) -> pd.DataFrame:
        """
        Execute a HogQL query and return results as a DataFrame.

        :param hogql_query: Raw HogQL query string
        :return: DataFrame with query results
        """
        if self.disable:
            logger.warning("PostHog disabled, returning empty DataFrame")
            return pd.DataFrame()

        query = {"kind": "HogQLQuery", "query": hogql_query}

        payload = {"query": query, "name": "test API"}
        logger.info(f"Executing HogQL query: {hogql_query}")

        data = self._make_request(json_data=payload)

        return pd.DataFrame(data.get("results", []), columns=data.get("columns", []))

    def count_unique_users(
        self,
        date_from: str = "now() - interval 6 day",
        date_to: str = "now()",
    ) -> pd.DataFrame:
        """
        Count unique users in the time period, inclusive (default is last 7 days from current date)

        :param date_from: start of time period, usually a date as string in format YYYY-MM-DD
        :param date_to: end of time period, usually a date as string in format YYYY-MM-DD
        :return: DataFrame with count of unique users

        """
        query = f"""
            SELECT COUNT(DISTINCT properties.distinct_id) FROM events
            WHERE timestamp >= {date_from}
            AND timestamp <= {date_to}
        """
        df = self.execute_query(query)
        return df


posthog_session = PostHogSession()

df = posthog_session.count_unique_users()
logger.info(df)
