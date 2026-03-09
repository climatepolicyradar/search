"""Shared date utilities for online metrics."""

from datetime import date, datetime, timedelta

from pydantic import BaseModel, model_validator

from search.log import get_logger

logger = get_logger(__name__)


class DateRange(BaseModel):
    """An inclusive range of dates for an API query."""

    date_from: date
    date_to: date

    @model_validator(mode="after")
    def check_date_order(self):
        """Check if the date range is valid"""
        if self.date_from > self.date_to:
            raise ValueError("Date from must be before date to")
        return self

    def get_earliest_datetime_of_range(self) -> datetime:
        """Get the earliest datetime of the date range."""
        return datetime.combine(self.date_from, datetime.min.time())

    def get_latest_datetime_of_range(self) -> datetime:
        """Get the latest datetime of the date range."""
        return datetime.combine(self.date_to, datetime.max.time())


class InvalidStartDateException(Exception):
    """Exception raised when the start date is invalid."""

    pass


def determine_prefect_flow_retention_anchor_date(date: date) -> date:
    """
    Determine the anchor date for retention metrics for automating in Prefect.

    The first of the previous month is the default anchor date.  If the first of the previous month is a weekend, the anchor date is the day before.
    """
    anchor_date = (date.replace(day=1) - timedelta(days=1)).replace(
        day=1
    )  # first day of previous month
    if anchor_date.weekday() == 5:  # Saturday
        anchor_date -= timedelta(days=1)
    elif anchor_date.weekday() == 6:  # Sunday
        anchor_date -= timedelta(days=2)
    return anchor_date
