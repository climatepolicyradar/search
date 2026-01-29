# search/online_metrics/__init__.py
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt, model_validator

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
    date_from: date
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_order(self) -> "OnlineMetricResult":
        """Validate that date_from is before or equal to date_to if both are provided."""
        if self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        return self
