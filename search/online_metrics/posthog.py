"""Helpers for interacting with PostHog"""

from datetime import date, timedelta
from typing import Any

import requests

from search.config import (
    POSTHOG_CPR_DOMAINS,
    POSTHOG_HOST,
    get_from_env_with_fallback,
)
from search.log import get_logger
from search.online_metrics import OnlineMetricResult
from search.online_metrics.date_utils import DateRange, InvalidStartDateException

logger = get_logger(__name__)


class PosthogNoResultsException(Exception):
    """An exception raised when a PostHog query returns no results."""

    def __init__(self, message: str = "PostHog query returned no results unexpectedly"):
        super().__init__(message)


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
        self.cpr_domains_hogql = (
            "(" + ", ".join(f"'{d}'" for d in POSTHOG_CPR_DOMAINS) + ")"
        )

    def execute_query(
        self, hogql_query: str, timeout: int = 20, raise_on_no_results: bool = True
    ) -> list[list[Any]]:
        """
        Execute a HogQL query and return raw results.

        :param hogql_query: Raw HogQL query string
        :param timeout: Timeout for the request in seconds
        :param raise_on_no_results: Whether to raise if the Posthog query returns empty
            results
        :return: List of result rows
        """
        query = {"kind": "HogQLQuery", "query": hogql_query}
        payload = {"query": query, "name": "test API"}
        logger.debug(f"Executing HogQL query: {hogql_query}")

        url = f"{self.host}/api/projects/{self.project_id}/query/"
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if raise_on_no_results and not results:
            raise PosthogNoResultsException()

        return results

    def _run_metric(
        self,
        metric_name: str,
        query: str,
        date_from: date,
        date_to: date | None = None,
    ) -> OnlineMetricResult:
        """
        Execute a HogQL query and wrap the first result in an OnlineMetricResult.

        :param metric_name: Name of the metric being calculated
        :param query: HogQL query string
        :param date_from: Start date for the metric
        :param date_to: Optional end date for the metric
        :return: OnlineMetricResult with the first scalar value from the query
        """
        results = self.execute_query(query)
        return OnlineMetricResult(
            metric=metric_name,
            query=query,
            value=results[0][0],
            date_from=date_from,
            date_to=date_to,
        )

    def calculate_percentage_of_users_who_search(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
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


        :param date_range: DateRange object specifying the inclusive date range
        :return: Percentage of users who searched in the time period as a float
        """

        # TODO: can we use this query elsewhere?
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
            WHERE timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                AND properties.consent IS NOT NULL
                AND event = '$pageview'
                AND properties.$host IN {self.cpr_domains_hogql}
        """
        return self._run_metric(
            "percentage_of_users_who_search",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )

    def calculate_percentage_of_users_who_download_search_results(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of total users who downloaded the results of their search in the time period, inclusive of start and end dates.

        "The total users" include only those with a pageview where the `consent` boolean is set.
        This means a user has either clicked 'accept' or 'reject' on the cookie banner, or
        they've viewed more than one page in a session.

        What's a search download?
        It refers specifically to 1. clicking "this search" and then "Download" in the resulting popup on the search results page.

        It does not include:
        - clicking to download the "whole database" as this is tracked by jotform, not Posthog.

        Note: this IS BREAKABLE if the link text changes.  It is queued to be updated with more robust frontend tracking (see SCI-677).

        :param date_range: DateRange object specifying the inclusive date range
        :return: Percentage of users who downloaded data in the time period
        """

        query = f"""
            WITH consent_set_users AS (
                SELECT DISTINCT distinct_id
                FROM events
                WHERE properties.consent IS NOT NULL
            )

            SELECT
                count(DISTINCT(
                    -- User is on search page and clicks an element with 'Download' text
                    -- (using Posthog autocapture)
                    if(
                        properties.$el_text = 'Download' AND properties.$current_url LIKE '%/search%',
                        events.distinct_id,
                        NULL
                    )
                )) /
                count(DISTINCT(consent_set_users.distinct_id)) * 100.0 AS search_downloaders_percentage
            FROM events
            INNER JOIN consent_set_users ON events.distinct_id = consent_set_users.distinct_id
            WHERE timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                AND properties.$host IN {self.cpr_domains_hogql}
        """
        return self._run_metric(
            "percentage_of_users_who_download_data",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )

    def calculate_percentage_of_searches_with_no_results(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of searches with no results in the time period, inclusive of start and end dates.

        What's a search with no results?
            It refers specifically to searches on the main search results page (where
            properties.$current_url LIKE '%/search%') that return no results.  See 'what is
            a search' in the calculate_percentage_of_users_who_search method for more details
            on defining a search.

        Each search event on the main search results page triggers an API request, which we
        track in PostHog as 'search:results_fetch' with a property 'total_family_hits' as a
        number.

        This is a calculation against the TOTAL number of searches, not a number of users.

        :param date_range: DateRange object specifying the inclusive date range
        :return: Percentage of searches with no results in the time period as a float
        """

        if date_range.date_from < date(2025, 10, 1):
            raise InvalidStartDateException(
                f"{date_range.date_from} is not a valid start date. Date must be after 2025-10-01, when this metric was created."
            )

        query = f"""
            SELECT
                count(DISTINCT(
                    if(
                        -- Include current_url like search here, as search:results_fetch
                        -- event can be fired again if a user goes to another page.
                        properties.total_family_hits = 0 AND properties.$current_url LIKE '%/search%',
                        distinct_id,
                        NULL
                    )
                )) /
                count(DISTINCT(distinct_id)) * 100.0 AS zero_results_rate
            FROM events
            WHERE timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                AND properties.$host IN {self.cpr_domains_hogql}
                -- This event is sent every time the frontend gets search results from
                -- the backend.
                AND event = 'search:results_fetch'
        """
        return self._run_metric(
            "percentage_of_searches_with_no_results",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )

    def calculate_7_day_searcher_retention_rate(
        self,
        date_from: date,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of [users whose searched] who return within 7 days of an input date.  The input date must be least 7 days before the current date.

        What's a searcher?
            A searcher is a user who has searched in the time period.  See 'what is a search'
            in the calculate_percentage_of_users_who_search method for more details on
            defining a search.

        As only users who accept cookies can be tracked cross-session, this calculation
        is only available for users with consent = True.

        What's a return?
        A return is counted if a user's distinct_id is associated with a different
        session_id within 7 days of the original session.

        :param date_from: datetime.date object of the start of the time period (inclusive)
        :return: Percentage of searchers who return within 7 days in the time period as a float
        """

        if date_from > date.today() - timedelta(days=7):
            raise InvalidStartDateException(
                f"{date_from} is not a valid input.  Date must be at least 7 days in the past.  Earliest valid date is {date.today() - timedelta(days=7)}."
            )

        query = f"""
        WITH consent_users AS (
            SELECT DISTINCT(distinct_id)
            FROM events
            WHERE properties.consent = true
        ),

        search_users AS (
            SELECT
                events.distinct_id,
                min(timestamp) as first_search_timestamp,
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
            events.timestamp < search_users.first_search_timestamp + interval 7 day
            AND events.timestamp > toStartOfDay(search_users.first_search_timestamp) + interval 1 day
            AND events.$session_id != search_users.search_session_id
            AND events.properties.$host IN {self.cpr_domains_hogql}
        )

        SELECT
            (SELECT count(DISTINCT(distinct_id)) FROM returning_users) /
            (SELECT count(DISTINCT(distinct_id)) FROM search_users) * 100.0 as retention_percentage_7_days

        """
        return self._run_metric(
            "percentage_of_searchers_who_return_within_7_days",
            query,
            date_from=date_from,
        )

    def calculate_30_day_searcher_retention_rate(
        self,
        date_from: date,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of [users whose searched] who return within 30 days of an input date.  The input date must be least 30 days before the current date.

        What's a searcher?
        A searcher is a user who has searched in the time period.  See 'what is a search'
        in the calculate_percentage_of_users_who_search method for more details on
        defining a search.

        As only users who accept cookies can be tracked cross-session, this calculation
        is only available for users with consent = True.

        What's a return?
        A return is counted if a user's distinct_id is associated with a different session_id within 30 days of the original session.

        :param date_from: start of time period (inclusive), a date as string in format YYYY-MM-DD
        :return: Percentage of searchers who return within 30 days in the time period as a float
        """

        if date_from > date.today() - timedelta(days=30):
            raise InvalidStartDateException(
                f"{date_from} is not a valid input.  Date must be at least 30 days in the past.  Earliest valid date is {date.today() - timedelta(days=30)}."
            )

        query = f"""
        WITH consent_users AS (
            SELECT DISTINCT(distinct_id)
            FROM events
            WHERE properties.consent = true
        ),

        search_users AS (
            SELECT
                events.distinct_id,
                min(timestamp) as first_search_timestamp,
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
            events.timestamp < search_users.first_search_timestamp + interval 30 day
            AND events.timestamp > toStartOfDay(search_users.first_search_timestamp) + interval 1 day
            AND events.$session_id != search_users.search_session_id
            AND events.properties.$host IN {self.cpr_domains_hogql}
        )

        SELECT
            (SELECT count(DISTINCT(distinct_id)) FROM returning_users) /
            (SELECT count(DISTINCT(distinct_id)) FROM search_users) * 100.0 as retention_percentage_30_days

        """
        return self._run_metric(
            "percentage_of_searchers_who_return_within_30_days",
            query,
            date_from=date_from,
        )

    def calculate_click_through_rate_from_search_results_page(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of users who clicked on a search result to a document or family page.

        What is 'clicking on a search result'?
        It refers specifically to either:
        1. clicking to a document family or document page from a search result on the main search results page.
        2. clicking to view text passages matching a search, then clicking to a document from the resulting sidebar.

        It does not include:
        1. only opening the sidebar, without clicking on to a document
        2. clicking search results within a document that are not on the main search results page.

        This only includes users where pageview events have the `consent` property set (not null)

        :param date_range: DateRange object specifying the inclusive date range
        :return: Percentage of users who clicked on a search result to a document or family page in the time period
        """
        query = f"""
            -- Get pageviews sorted by timestamp and user
            WITH ranked_pageviews AS (
            SELECT
                distinct_id,
                properties.$current_url as current_url,
                timestamp,
                row_number() OVER (PARTITION BY distinct_id ORDER BY timestamp) as rn
            FROM events
            WHERE
                event = '$pageview'
                AND properties.consent IS NOT NULL
                AND timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                AND properties.$host IN {self.cpr_domains_hogql}
            ),

            pageviews_with_next AS (
                SELECT
                    p1.distinct_id,
                    p1.current_url,
                    p2.current_url as next_url
                FROM ranked_pageviews p1
                LEFT JOIN ranked_pageviews p2
                    ON p1.distinct_id = p2.distinct_id
                    AND p2.rn = p1.rn + 1
            ),

            -- Search users: first pageview is search
            search_users AS (
                SELECT DISTINCT distinct_id
                FROM pageviews_with_next
                WHERE current_url LIKE '%/search%'
            ),

            -- Clickthrough users: first pageview is search, second pageview is
            -- document or family page
            clickthrough_users AS (
                SELECT DISTINCT distinct_id
                FROM pageviews_with_next
                WHERE
                    current_url LIKE '%/search%'
                    AND (next_url LIKE '%/document/%' OR next_url LIKE '%/documents/%')
            )

            SELECT
                count(DISTINCT clickthrough_users.distinct_id) / count(DISTINCT search_users.distinct_id) * 100.0 AS click_through_rate
            FROM search_users
            LEFT JOIN clickthrough_users ON search_users.distinct_id = clickthrough_users.distinct_id

        """
        return self._run_metric(
            "percentage_of_users_who_clicked_on_a_search_result_to_a_document_or_family_page",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )

    def calculate_click_through_rate_from_search_results_page_with_dwell_time(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of users who clicked on a search result to a document or family page and then stayed on that document or family page for 30 seconds or more.

        This is the same as the calculate_click_through_rate_from_search method, but it
        also includes when users click from to a family then straight to a document in less than 30 seconds, as long as they spend at least 30 seconds on the document.

        This only includes users where pageview events have the `consent` property set (not null)

        :param date_range: DateRange object specifying the inclusive date range
        :return: CTR with dwell time >=30 seconds
        """

        query = f"""
            WITH ranked_pageviews AS (
            SELECT
                distinct_id,
                properties.$current_url as current_url,
                timestamp,
                row_number() OVER (PARTITION BY distinct_id ORDER BY timestamp) as rn
            FROM events
            WHERE
                event = '$pageview'
                AND properties.consent IS NOT NULL
                AND timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                AND properties.$host IN {self.cpr_domains_hogql}
            ),

            pageviews_with_next AS (
                SELECT
                    p1.distinct_id,
                    p1.current_url,
                    p2.current_url as next_url,
                    p3.current_url as next_next_url,
                    dateDiff('second', p2.timestamp, p3.timestamp) as next_dwell_time,
                    dateDiff('second', p3.timestamp, p4.timestamp) as next_next_dwell_time
                FROM ranked_pageviews p1
                -- Self joins to get the next 3 pageviews for each pageview
                LEFT JOIN ranked_pageviews p2 ON p1.distinct_id = p2.distinct_id AND p2.rn = p1.rn + 1
                LEFT JOIN ranked_pageviews p3 ON p1.distinct_id = p3.distinct_id AND p3.rn = p1.rn + 2
                LEFT JOIN ranked_pageviews p4 ON p1.distinct_id = p4.distinct_id AND p4.rn = p1.rn + 3
            ),

            search_users AS (
                SELECT DISTINCT distinct_id
                FROM pageviews_with_next
                WHERE current_url LIKE '%/search%'
            ),

            clickthrough_users AS (
                SELECT DISTINCT distinct_id
                FROM pageviews_with_next
                WHERE
                    current_url LIKE '%/search%'
                    AND (
                        -- Direct: search -> document page with 30+ seconds
                        ((next_url LIKE '%/document/%' OR next_url LIKE '%/documents/%')
                        AND next_dwell_time >= 30)
                        OR
                        -- Two-step: search -> document (family) -> documents with 30+ seconds on documents
                        (next_url LIKE '%/document/%'
                        AND next_next_url LIKE '%/documents/%'
                        AND next_next_dwell_time >= 30)
                    )
            )

            SELECT
                count(DISTINCT clickthrough_users.distinct_id) / count(DISTINCT search_users.distinct_id) * 100.0 AS click_through_rate
            FROM search_users
            LEFT JOIN clickthrough_users ON search_users.distinct_id = clickthrough_users.distinct_id
        """
        return self._run_metric(
            "percentage_of_users_who_clicked_on_a_search_result_to_a_document_or_family_page_with_at_least_30s_dwell_time",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )

    def calculate_click_through_rate_from_search_results_page_for_top_5_results(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of users who clicked on a search result in the top 5 to a family page.

        What does this metric measure?
        It measures the percentage of unique users who clicked on a search result to a
        family page for the top 5 results.  Right now, this ONLY includes clicking directly
        on a family page link, not clicking to view a document or family after viewing the
        passage match sidebar.
        (see https://linear.app/climate-policy-radar/issue/APP-1610/facilitate-better-analytics-by-including-more-context-in-dom-elements).

        This is ONLY available for data after the 29th of January 2026.

        This only includes users where pageview events have the `consent` property set (not null)

        :param date_range: DateRange object specifying the inclusive date range
        :return: Percentage of users who clicked on a search result to a document or family page in the time period
        """

        if date_range.date_from < date(2026, 1, 29):
            raise InvalidStartDateException(
                f"{date_range.date_from} is not a valid input.  Start date for this metric must be on or after the 29th of January 2026."
            )
        query = f"""
            WITH ranked_pageviews AS (
                SELECT
                    distinct_id,
                    properties.$current_url as current_url,
                    timestamp,
                    row_number() OVER (PARTITION BY distinct_id ORDER BY timestamp) as rn
                FROM events
                WHERE
                    event = '$pageview'
                    AND properties.consent IS NOT NULL
                    AND timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                    AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                    AND properties.$host IN {self.cpr_domains_hogql}
            ),
            search_users AS (
                SELECT DISTINCT distinct_id
                FROM ranked_pageviews
                WHERE current_url LIKE '%/search%'
            ),
            clickthrough_users AS (
                SELECT DISTINCT distinct_id
                FROM events
                WHERE
                    event = '$autocapture'
                    AND properties.$event_type = 'click'
                    AND properties.$current_url LIKE '%/search%'
                    AND properties.`position-total` IN ('1', '2', '3', '4', '5')
                    AND timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                    AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                    AND properties.$host IN {self.cpr_domains_hogql}
            )
            SELECT
                count(DISTINCT clickthrough_users.distinct_id) / count(DISTINCT search_users.distinct_id) * 100.0 AS click_through_rate
            FROM search_users
            LEFT JOIN clickthrough_users ON search_users.distinct_id = clickthrough_users.distinct_id

        """
        return self._run_metric(
            "percentage_of_users_who_clicked_on_a_search_result_to_a_document_or_family_page",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )

    def calculate_click_through_rate_from_search_results_page_for_top_5_results_with_dwell_time(
        self,
        date_range: DateRange,
    ) -> OnlineMetricResult:
        """
        Calculate the percentage of users who clicked on a search result in the top 5 to a family page then stayed on that family or one of its documents for 30 seconds or more.

        What does this metric measure?
        It measures the percentage of unique users who clicked on a search result to a family page for the top 5 results and then stayed on that family or one of its documents for 30 seconds or more.  Right now, this ONLY includes clicking directly on a family page link, not clicking to view a document or family after viewing the passage match sidebar. (see https://linear.app/climate-policy-radar/issue/APP-1610/facilitate-better-analytics-by-including-more-context-in-dom-elements).  This is ONLY available for data after the 29th of January 2026.

        This only includes users where pageview events have the `consent` property set (not null)

        :param date_range: DateRange object specifying the inclusive date range
        :return: Percentage of users who clicked on a search result to a document or family page in the time period as a float
        """

        if date_range.date_from < date(2026, 1, 29):
            raise InvalidStartDateException(
                f"{date_range.date_from} is not a valid input.  Start date for this metric must be on or after the 29th of January 2026."
            )

        query = f"""
            -- Step 1: Get all pageviews with row numbers for sequential ordering
            WITH ranked_pageviews AS (
                SELECT
                    distinct_id,
                    properties.$current_url as current_url,
                    timestamp,
                    -- Row number allows us to find the "next" pageview for each user
                    row_number() OVER (PARTITION BY distinct_id ORDER BY timestamp) as rn
                FROM events
                WHERE
                    event = '$pageview'
                    AND properties.consent IS NOT NULL
                    AND timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                    AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                    AND properties.$host IN {self.cpr_domains_hogql}
            ),
            -- Step 2: Identify all users who visited a search page (our denominator)
            search_users AS (
                SELECT DISTINCT distinct_id
                FROM ranked_pageviews
                WHERE current_url LIKE '%/search%'
            ),
            -- Step 3: Find all qualifying autocapture click events on search pages
            autocapture_clicks AS (
                SELECT
                    distinct_id,
                    timestamp as click_timestamp
                FROM events
                WHERE
                    event = '$autocapture'
                    AND properties.$event_type = 'click'
                    AND properties.$current_url LIKE '%/search%'
                    -- Position 1-5 in search results (first page only, offset = 0)
                    AND properties.`position-total` IN ('1', '2', '3', '4', '5')
                    AND timestamp >= '{date_range.get_earliest_datetime_of_range()}'
                    AND timestamp <= '{date_range.get_latest_datetime_of_range()}'
                    AND properties.$host IN {self.cpr_domains_hogql}
            ),
            -- Step 4: For each click, find the immediate next pageview (must be a /document/ page)
            clicks_with_next_pageview AS (
                SELECT
                    ac.distinct_id,
                    ac.click_timestamp,
                    -- Find the earliest pageview timestamp after the click
                    MIN(p1.timestamp) as next_pageview_timestamp,
                    -- Get the URL of that earliest pageview using argMin (returns value where timestamp is minimum)
                    argMin(p1.current_url, p1.timestamp) as next_pageview_url,
                    -- Get the row number of that earliest pageview so we can find subsequent pages
                    argMin(p1.rn, p1.timestamp) as next_pageview_rn
                FROM autocapture_clicks ac
                INNER JOIN ranked_pageviews p1
                    ON ac.distinct_id = p1.distinct_id
                    -- Only pageviews that happened after the click
                    AND p1.timestamp > ac.click_timestamp
                    -- Only pageviews to /document/ pages (the click must lead to a document)
                    AND p1.current_url LIKE '%/document/%'
                GROUP BY ac.distinct_id, ac.click_timestamp
            ),
            -- Step 5: Determine which clicks resulted in sufficient engagement (30+ second dwell time)
            clickthrough_users AS (
                SELECT DISTINCT c.distinct_id
                FROM clicks_with_next_pageview c
                -- Join to get the page AFTER the /document/ page (p2)
                LEFT JOIN ranked_pageviews p2
                    ON p2.distinct_id = c.distinct_id AND p2.rn = c.next_pageview_rn + 1
                -- Join to get the page AFTER p2 (p3) - needed for scenario 2
                LEFT JOIN ranked_pageviews p3
                    ON p3.distinct_id = p2.distinct_id AND p3.rn = p2.rn + 1
                WHERE
                    -- Scenario 1: User stayed on the /document/ page for 30+ seconds
                    -- (Time from landing on /document/ to next pageview or now)
                    dateDiff('second', c.next_pageview_timestamp, COALESCE(p2.timestamp, now())) >= 30
                    OR
                    -- Scenario 2: User went from /document/ to /documents/ and stayed there 30+ seconds
                    -- (Even if they left /document/ quickly)
                    (p2.current_url LIKE '%/documents/%' AND dateDiff('second', p2.timestamp, COALESCE(p3.timestamp, now())) >= 30)
            )
            -- Step 6: Calculate click-through rate as percentage
            SELECT
                -- Number of users who clicked and engaged / total users who visited search
                count(DISTINCT clickthrough_users.distinct_id) / count(DISTINCT search_users.distinct_id) * 100.0 AS click_through_rate
            FROM search_users
            LEFT JOIN clickthrough_users ON search_users.distinct_id = clickthrough_users.distinct_id

        """
        return self._run_metric(
            "percentage_of_users_who_clicked_on_a_search_result_to_a_document_or_family_page",
            query,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )
