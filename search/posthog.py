"""Helpers for interacting with PostHog"""

# TODO filter internal users
# TODO validate date inputs

from typing import Any

import requests
from pydantic import NonNegativeFloat, NonNegativeInt

from search.config import (
    POSTHOG_HOST,
    POSTHOG_PARAM_NAME,
    POSTHOG_PROJECT_ID,
    get_from_env_with_fallback,
)
from search.log import get_logger

logger = get_logger(__name__)


class Count(NonNegativeInt):
    """A count of a value returned from PostHog"""


class Percentage(NonNegativeFloat):
    """A percentage value returned from PostHog"""


class PostHogSession:
    """Session for querying PostHog analytics data."""

    def __init__(self) -> None:
        self.api_key = get_from_env_with_fallback(
            var_name="POSTHOG_API_KEY", ssm_name=POSTHOG_PARAM_NAME
        )
        self.host = POSTHOG_HOST
        self.project_id = POSTHOG_PROJECT_ID

    def _make_request(
        self, endpoint: str = "query/", json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated request to PostHog API."""

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

    def execute_query(self, hogql_query: str) -> list[list[Any]]:
        """
        Execute a HogQL query and return raw results.

        :param hogql_query: Raw HogQL query string
        :return: List of result rows
        """
        query = {"kind": "HogQLQuery", "query": hogql_query}
        payload = {"query": query, "name": "test API"}
        logger.info(f"Executing HogQL query: {hogql_query}")

        data = self._make_request(json_data=payload)
        return data.get("results", [])

    def count_unique_users(
        self,
        date_from: str = "now() - interval 6 day",
        date_to: str = "now()",
    ) -> Count:
        """
        Placeholder method: Count unique users in the time period, inclusive (default is last 7 days from current date)

        :param date_from: start of time period, usually a date as string in format YYYY-MM-DD
        :param date_to: end of time period, usually a date as string in format YYYY-MM-DD
        :return: Count of unique users as a NonNegativeInt in the time period

        """
        query = f"""
            SELECT COUNT(DISTINCT properties.distinct_id) FROM events
            WHERE timestamp >= {date_from}
            AND timestamp <= {date_to}
        """
        results = self.execute_query(query)
        if not results:
            raise ValueError("PostHog query returned no results unexpectedly")
        return Count(results[0][0])

    def calculate_percentage_of_users_who_search(
        self,
        date_from: str = "now() - interval 6 day",
        date_to: str = "now()",
    ) -> Percentage:
        """
        Calculate the percentage of users who searched (NOT within a document) in the time period.

        What's a search?
        A search is any filtered/unfiltered view of the results.  In that context, we consider search terms, page numbers, and regular topic/geogrraphy/etc filters are filters.  Thus, all of the following are valid search events:

        - hitting the SERP (search engine results page) with some search terms e.g., "https://app.climatepolicyradar.org/search?q=kenya"
        - going to the second page of results (this triggers URL change and API request)
        - running a 'search' with no search terms, only filters
        - running a 'search' with no search terms, no filters
        - landing on the search page as the first pageview of a session

        what's not a search
        - searching within a document
            - this is a search, but it's not the sort of search that most people are asking questions about.  It should be its own event, counted differently.
        -clicking on a document from the search results (this triggers an API request)
            - this is an event which appears in the user's search journey, but it's not a search.

        The users include those with a pageview where the `consent` boolean is set.

        See https://www.notion.so/climatepolicyradar/What-counts-as-a-search-2e89109609a48020b247fb9f19fac1de


        :param date_from: start of time period, usually a date as string in format YYYY-MM-DD
        :param date_to: end of time period, usually a date as string in format YYYY-MM-DD
        :return: Percentage of users who searched in the time period as a float
        """
        query = f"""
            SELECT 
                count(Distinct(
                    if(
                        properties.$current_url LIKE '%/search%',
                        distinct_id,
                        NULL
                    )
                )) / count(Distinct(distinct_id)) * 100.0 AS search_percentage
            FROM events
            WHERE timestamp >= {date_from}
                AND timestamp <= {date_to}
                AND properties.consent IS NOT NULL
                AND event = '$pageview'
        """
        results = self.execute_query(query)
        if not results:
            raise ValueError("PostHog query returned no results unexpectedly")
        return Percentage(results[0][0])


session = PostHogSession()
percentage = session.calculate_percentage_of_users_who_search()
logger.info(f"Percentage of users who searched: {percentage}")
