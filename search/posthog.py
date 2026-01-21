"""Helpers for interacting with PostHog"""

from datetime import date
from typing import Any

import requests
from pydantic import (
    BaseModel,
    NonNegativeFloat,
    NonNegativeInt,
    ValidationError,
    model_validator,
)

from search.config import (
    POSTHOG_CPR_DOMAINS,
    POSTHOG_HOST,
    get_from_env_with_fallback,
)
from search.log import get_logger

logger = get_logger(__name__)


class Count(NonNegativeInt):
    """A count of a value returned from PostHog"""


class Percentage(NonNegativeFloat):
    """A percentage value returned from PostHog"""


class DateRange(BaseModel):
    """An inclusive range of dates for a HogQL query"""

    date_from: date
    date_to: date

    @model_validator(mode="after")
    def check_date_order(self):
        """Check if the date range is valid"""
        if self.date_from > self.date_to:
            raise ValueError("Date from must be before date to")
        return self


class PostHogSession:
    """Session for querying PostHog analytics data."""

    def __init__(self) -> None:
        self.api_key = get_from_env_with_fallback(
            var_name="POSTHOG_API_KEY", ssm_name="posthog_readonly"
        )
        self.host = POSTHOG_HOST
        self.project_id = get_from_env_with_fallback(
            var_name="POSTHOG_PROJECT_ID", ssm_name="posthog_project_id"
        )
        # to filter out internal users mainly, in HogQL queries
        self.cpr_domains = "(" + ", ".join(f"'{d}'" for d in POSTHOG_CPR_DOMAINS) + ")"

    def _check_date_range(self, date_from: str, date_to: str) -> None:
        """Check if a date range input is valid for a HogQL query"""

        try:
            DateRange(date_from=date_from, date_to=date_to)
            logger.debug(f"Date range {date_from} and {date_to} is valid")
        except ValidationError as e:
            logger.error(f"Error validating date range: {date_from} and {date_to}: {e}")
            raise

    def execute_query(self, hogql_query: str) -> list[list[Any]]:
        """
        Execute a HogQL query and return raw results.

        :param hogql_query: Raw HogQL query string
        :return: List of result rows
        """
        query = {"kind": "HogQLQuery", "query": hogql_query}
        payload = {"query": query, "name": "test API"}
        logger.info(f"Executing HogQL query: {hogql_query}")

        url = f"{self.host}/api/projects/{self.project_id}/query/"
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        return data.get("results", [])

    def calculate_percentage_of_users_who_search(
        self,
        date_from: str,
        date_to: str,
    ) -> Percentage:
        """
        Calculate the percentage of users who searched (NOT within a document) in the time period, inclusive of start and end dates.

        What's a search?
        A search is any filtered/unfiltered view of the results.  In that context, we consider search terms, page numbers, and regular topic/geography/etc filters are filters.  Thus, all of the following are valid search events:

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

        "The total users" include only those with a pageview where the `consent` boolean is set.

        See https://www.notion.so/climatepolicyradar/What-counts-as-a-search-2e89109609a48020b247fb9f19fac1de


        :param date_from: start of time period (inclusive), a date as string in format YYYY-MM-DD
        :param date_to: end of time period (exclusive), a date as string in format YYYY-MM-DD
        :return: Percentage of users who searched in the time period as a float
        """

        self._check_date_range(date_from, date_to)
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
            WHERE timestamp >= '{date_from} 00:00:00'
                AND timestamp <= '{date_to} 23:59:59'
                AND properties.consent IS NOT NULL
                AND event = '$pageview'
                AND properties.$host IN {self.cpr_domains}
        """
        results = self.execute_query(query)
        if not results:
            raise ValueError("PostHog query returned no results unexpectedly")
        return Percentage(results[0][0])

    def calculate_percentage_of_users_who_download_data(
        self,
        date_from: str,
        date_to: str,
    ) -> Percentage:
        """
        Calculate the percentage of total users who downloaded data in the time period, inclusive of start and end dates.

        What's a search download?
        It refers specifically to 1. clicking "this search" and then "Download" in the resulting popup on the search results page.

        It does not include:
        - clicking to download the "whole database" as this is tracked by jotform, not Posthog.

        Note: this IS BREAKABLE if the link text changes.  It is queued to be updated with more robust frontend tracking (see SCI-677).

        "The total users" include only those with a pageview where the `consent` boolean is set.

        :param date_from: start of time period (inclusive), a date as string in format YYYY-MM-DD
        :param date_to: end of time period (exclusive), a date as string in format YYYY-MM-DD
        :return: Percentage of users who downloaded data in the time period as a float
        """
        self._check_date_range(date_from, date_to)
        query = f"""
            WITH consent_set_users AS (
                SELECT DISTINCT distinct_id
                FROM events 
                WHERE properties.consent IS NOT NULL
            )

            SELECT 
                count(DISTINCT(
                    if(
                        properties.$el_text = 'Download' AND properties.$current_url LIKE '%/search%',
                        events.distinct_id,
                        NULL
                    )
                )) /
                count(DISTINCT(consent_set_users.distinct_id)) * 100.0 AS search_downloaders_percentage
            FROM events
            INNER JOIN consent_set_users ON events.distinct_id = consent_set_users.distinct_id
            WHERE timestamp >= '{date_from} 00:00:00'
                AND timestamp <= '{date_to} 23:59:59'
                AND properties.$host IN {self.cpr_domains}
        """
        results = self.execute_query(query)
        if not results:
            raise ValueError("PostHog query returned no results unexpectedly")
        return Percentage(results[0][0])

    def calculate_percentage_of_searches_with_no_results(
        self,
        date_from: str,
        date_to: str,
    ) -> Percentage:
        """
        Calculate the percentage of searches with no results in the time period, inclusive of start and end dates.

        What's a search with no results?
        It refers specifically to searches on the main search results page (where properties.$current_url LIKE '%/search%') that return no results.  See 'what is a search' in the calculate_percentage_of_users_who_search method for more details on defining a search.

        Each search event on the main search results page triggers an API request, which we track in PostHog as 'search:results_fetch' with a property 'total_family_hits' as a number.  This event was created in October 2025.

        This is a calculation against the TOTAL number of searches, not a number of users.

        :param date_from: start of time period (inclusive), a date as string in format YYYY-MM-DD
        :param date_to: end of time period (exclusive), a date as string in format YYYY-MM-DD
        :return: Percentage of searches with no results in the time period as a float
        """
        self._check_date_range(date_from, date_to)
        query = f"""
            SELECT 
                count(DISTINCT(
                    if(
                        properties.total_family_hits = 0 AND properties.$current_url LIKE '%/search%',
                        distinct_id,
                        NULL
                    )
                )) /
                count(DISTINCT(distinct_id)) * 100.0 AS zero_results_rate
            FROM events
            WHERE timestamp >= '{date_from} 00:00:00'
                AND timestamp <= '{date_to} 23:59:59'
                AND properties.$host IN {self.cpr_domains}
                AND event = 'search:results_fetch'
        """
        results = self.execute_query(query)
        if not results:
            raise ValueError("PostHog query returned no results unexpectedly")
        return Percentage(results[0][0])

    def calculate_7_day_searcher_retention_rate(
        self,
        date_from: str,
    ) -> Percentage:
        """
        Calculate the percentage of [users whose searched] who return within 7 days of an input date.  The input date must be least 7 days before the current date.

        What's a searcher?
        A searcher is a user who has searched in the time period.  See 'what is a search' in the calculate_percentage_of_users_who_search method for more details on defining a search.

        As only users who accept cookies can be tracked cross-session, this calculation is only available for users with consent = True.

        What's a return?
        A return is counted if a user's distinct_id is associated with a different session_id within 7 days of the original session.

        :param date_from: start of time period (inclusive), a date as string in format YYYY-MM-DD
        :return: Percentage of searchers who return within 7 days in the time period as a float
        """
        # TODO: validate the input date and that it is at least 7 days before the current date
        # TODO: ponder if we should include sessions on the same day as the start date, but after the original search session, or only from the next day.  The difference is appreciable.

        query = f"""
        WITH consent_users AS (
            SELECT DISTINCT(distinct_id)
            FROM events 
            WHERE properties.consent = true
        ),

        search_users AS (
            SELECT 
                events.distinct_id,
                min(timestamp) as first_search_date,
                argMin(properties.$session_id, timestamp) as search_session_id
            FROM events
            INNER JOIN consent_users ON events.distinct_id = consent_users.distinct_id
            WHERE 
                properties.$current_url LIKE '%/search%'
                AND timestamp >= '{date_from} 00:00:00' 
                AND timestamp < '{date_from} 00:00:00' + interval 1 day
            GROUP BY events.distinct_id
        ),

        returning_users AS (SELECT
            distinct(search_users.distinct_id)
        FROM search_users
        INNER JOIN events on search_users.distinct_id = events.distinct_id
        WHERE
            events.timestamp < search_users.first_search_date + interval 6 day
            AND events.timestamp > search_users.first_search_date
            AND events.$session_id != search_users.search_session_id
            AND events.properties.$host IN {self.cpr_domains}
        )

        SELECT 
            (SELECT count(DISTINCT(distinct_id)) FROM returning_users) /
            (SELECT count(DISTINCT(distinct_id)) FROM search_users) * 100.0 as retention_percentage_7_days,


        """
        results = self.execute_query(query)
        if not results:
            raise ValueError("PostHog query returned no results unexpectedly")
        return Percentage(results[0][0])
