"""Shared date utilities for online metrics."""

from datetime import date, timedelta

from pydantic import BaseModel, ValidationError, model_validator

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


def check_date_range(date_from: str | date, date_to: str | date) -> DateRange:
    """Check if a date range is valid for an API query."""
    try:
        DateRange(date_from=date_from, date_to=date_to)
        logger.debug(f"Date range {date_from} and {date_to} is valid")
        return DateRange(date_from=date_from, date_to=date_to)
    except ValidationError as e:
        logger.error(f"Error validating date range: {date_from} and {date_to}: {e}")
        raise


def check_date_at_least_n_days_ago(input_date: str, days_ago: int) -> None:
    """Validate that a date string is valid and at least n days in the past."""
    try:
        parsed_date = date.fromisoformat(input_date)
    except ValueError:
        raise ValueError(
            f"Invalid date format: '{input_date}'. Expected YYYY-MM-DD format."
        )

    cutoff_date = date.today() - timedelta(days=days_ago)
    if parsed_date > cutoff_date:
        raise ValueError(
            f"Date '{input_date}' must be at least {days_ago} days in the past. "
            f"Earliest valid date is {cutoff_date.isoformat()}."
        )
