# search/online_metrics/__init__.py
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt, model_validator

from search.online_metrics.date_utils import DateRange

# Value types (moved from posthog.py and grafana.py)
Count = Annotated[
    NonNegativeInt,
    Field(description="A count of a value returned from PostHog or Grafana"),
]

Percentage = Annotated[
    NonNegativeFloat, Field(description="A percentage value returned from PostHog")
]

TimeMilliseconds = Annotated[
    NonNegativeFloat,
    Field(description="A time value in milliseconds returned from Grafana"),
]


class PercentileResult(BaseModel):
    """A result from a percentile query"""

    p50: TimeMilliseconds
    p95: TimeMilliseconds
    p99: TimeMilliseconds


class OnlineMetricResult(BaseModel):
    """A result from an online metric query."""

    metric: str
    query: str
    value: PercentileResult | Percentage | Count
    date_range: DateRange | None = None
    date_from: date | None = None

    @model_validator(mode="after")
    def validate_date_input(self) -> "OnlineMetricResult":
        """Validate that at least one date input is provided."""
        if self.date_range is None and self.date_from is None:
            raise ValueError("Either date_range or date_from must be provided")
        return self
