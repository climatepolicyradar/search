r"""
Run all PostHog online metrics and print results to stdout.

Usage::

    uv run scripts/run_online_metrics.py \\
        --date-from 2026-01-01 \\
        --date-to 2026-01-31 \\
        --retention-date 2025-12-20

``--date-from`` and ``--date-to`` define the inclusive window for range-based
metrics (search rate, download rate, zero-results rate, click-through rates).

``--retention-date`` is the anchor date for 7-day and 30-day retention metrics.
It must be at least 30 days in the past.  If omitted, it defaults to 30 days
before today.
"""

import argparse
import sys
from datetime import date, timedelta

from search.online_metrics.date_utils import DateRange, InvalidStartDateException
from search.online_metrics.posthog import PosthogNoResultsException, PostHogSession


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    :return: Parsed arguments namespace.
    :rtype: argparse.Namespace
    """
    today = date.today()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--date-from",
        type=date.fromisoformat,
        default=today.replace(day=1),
        metavar="YYYY-MM-DD",
        help="Start of the date range for range-based metrics (default: first day of current month).",
    )
    parser.add_argument(
        "--date-to",
        type=date.fromisoformat,
        default=today - timedelta(days=1),
        metavar="YYYY-MM-DD",
        help="End of the date range for range-based metrics (default: yesterday).",
    )
    parser.add_argument(
        "--retention-date",
        type=date.fromisoformat,
        default=today - timedelta(days=30),
        metavar="YYYY-MM-DD",
        help="Anchor date for retention metrics (default: 30 days ago). Must be at least 30 days in the past.",
    )
    return parser.parse_args()


def run_metric(label: str, fn, *args, unit: str = "%", **kwargs):
    """
    Run a single metric function and print its result, handling known exceptions.

    :param label: Human-readable name for the metric.
    :type label: str
    :param fn: Callable that returns an OnlineMetricResult.
    :param unit: Unit string appended to the printed value (default: ``"%"``).
    :type unit: str
    :param args: Positional arguments forwarded to ``fn``.
    :param kwargs: Keyword arguments forwarded to ``fn``.
    """
    try:
        result = fn(*args, **kwargs)
        print(f"  {label}: {result.value:.2f}{unit}")
    except InvalidStartDateException as e:
        print(f"  {label}: SKIPPED — {e}")
    except PosthogNoResultsException as e:
        print(f"  {label}: NO RESULTS — {e}")
    except Exception as e:
        print(f"  {label}: ERROR — {e}", file=sys.stderr)


def main() -> None:
    """Entry point: run all metrics and print results."""
    args = parse_args()
    date_range = DateRange(date_from=args.date_from, date_to=args.date_to)
    retention_date = args.retention_date

    session = PostHogSession()

    print(f"\nRange-based metrics ({args.date_from} to {args.date_to})")
    print("-" * 55)
    run_metric(
        "% users who search",
        session.calculate_percentage_of_users_who_search,
        date_range,
    )
    run_metric(
        "% users who download data",
        session.calculate_percentage_of_users_who_download_data,
        date_range,
    )
    run_metric(
        "% searches with no results",
        session.calculate_percentage_of_searches_with_no_results,
        date_range,
    )
    run_metric(
        "% users who click through (any result)",
        session.calculate_click_through_rate_from_search_results_page,
        date_range,
    )
    run_metric(
        "% users who click through (any result, 30s dwell)",
        session.calculate_click_through_rate_from_search_results_page_with_dwell_time,
        date_range,
    )
    run_metric(
        "% users who click through (top 5)",
        session.calculate_click_through_rate_from_search_results_page_for_top_5_results,
        date_range,
    )
    run_metric(
        "% users who click through (top 5, 30s dwell)",
        session.calculate_click_through_rate_from_search_results_page_for_top_5_results_with_dwell_time,
        date_range,
    )

    print(f"\nRetention metrics (anchor date: {retention_date})")
    print("-" * 55)
    run_metric(
        "7-day searcher retention",
        session.calculate_7_day_searcher_retention_rate,
        retention_date,
    )
    run_metric(
        "30-day searcher retention",
        session.calculate_30_day_searcher_retention_rate,
        retention_date,
    )

    print()


if __name__ == "__main__":
    main()
