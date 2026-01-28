"""Shared date utilities for online metrics."""

from datetime import date, datetime

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

    def get_earliest_time_of_date(self) -> datetime:
        """Get the earliest time (midnight) of a given date."""
        return datetime.combine(self.date_from, datetime.min.time())

    def get_latest_time_of_date(self) -> datetime:
        """Get the latest time (end of day) of a given date."""
        return datetime.combine(self.date_to, datetime.max.time())


class InvalidStartDateException(Exception):
    """Exception raised when the start date is invalid."""

    pass
