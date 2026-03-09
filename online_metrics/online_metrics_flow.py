"""Prefect flow for collecting online metrics from PostHog and Grafana and logging to W&B."""

from datetime import date, timedelta

from prefect import flow, get_run_logger
from search.date_utils import determine_prefect_flow_retention_anchor_date
from search.online_metrics import OnlineMetricResult
from search.online_metrics.date_utils import DateRange, InvalidStartDateException
from search.online_metrics.posthog import PosthogNoResultsException, PostHogSession
from search.weights_and_biases import WandbSession


@flow(name="collect_online_metrics")
def collect_online_metrics(
    date_from: date | None = None,
    date_to: date | None = None,
    retention_date: date | None = None,
):
    """Collect all PostHog online metrics and log to Weights & Biases."""
    logger = get_run_logger()

    today = date.today()
    date_from = date_from or (today.replace(day=1) - timedelta(days=1)).replace(
        day=1
    )  # start of previous calendar month
    date_to = date_to or (
        today.replace(day=1) - timedelta(days=1)
    )  # end of previous calendar month
    retention_date = retention_date or determine_prefect_flow_retention_anchor_date(
        today
    )

    date_range = DateRange(date_from=date_from, date_to=date_to)

    session = PostHogSession()

    # Collect all results first, before any W&B logging
    results: list[OnlineMetricResult] = []

    def run_metric(label: str, fn, *args):
        try:
            result = fn(*args)
            results.append(result)
            logger.info(f"{label}: {result.value:.2f}")
        except InvalidStartDateException as e:
            logger.warning(f"{label}: SKIPPED — {e}")
        except PosthogNoResultsException as e:
            logger.warning(f"{label}: NO RESULTS — {e}")
        except Exception as e:
            logger.error(f"{label}: ERROR — {e}")

    logger.info(f"Collecting range-based metrics ({date_from} to {date_to})")
    run_metric(
        "% users who search",
        session.calculate_percentage_of_users_who_search,
        date_range,
    )
    run_metric(
        "% users who download data",
        session.calculate_percentage_of_users_who_download_search_results,
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

    logger.info(f"Collecting retention metrics (anchor date: {retention_date})")
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
    run_metric(
        "30-day non-searcher retention",
        session.calculate_30_day_non_searcher_retention_rate,
        retention_date,
    )
    run_metric(
        "7-day return-to-search retention",
        session.calculate_7_day_return_to_search_retention_rate,
        retention_date,
    )
    run_metric(
        "30-day return-to-search retention",
        session.calculate_30_day_return_to_search_retention_rate,
        retention_date,
    )

    # Now log all results to W&B (after all PostHog and Grafanaqueries complete)
    logger.info(f"Logging {len(results)} metrics to Weights & Biases")
    wb = WandbSession()
    wb.log_online_metric_results(results, date_from, date_to, retention_date)
    logger.info("Finished logging to W&B")


if __name__ == "__main__":
    import typer

    def main(
        date_from: str | None = typer.Option(None, help="Start date (YYYY-MM-DD)"),
        date_to: str | None = typer.Option(None, help="End date (YYYY-MM-DD)"),
        retention_date: str | None = typer.Option(
            None, help="Retention anchor date (YYYY-MM-DD)"
        ),
    ):
        collect_online_metrics(
            date_from=date.fromisoformat(date_from) if date_from else None,
            date_to=date.fromisoformat(date_to) if date_to else None,
            retention_date=date.fromisoformat(retention_date)
            if retention_date
            else None,
        )

    typer.run(main)
