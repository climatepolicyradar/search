"""
How a feed fails, and what a batch reports back.

The error and result types `vespa_feeder` produces, split out so the flow
module holds behaviour rather than shape. The results live here with the
errors because the two are one cluster: `FailedDocument` composes into the
two error types, those union into `VespaError`, which `FeedResult` holds,
which `VespaFeederFailed` carries. Splitting the exceptions from the results
they report on would only mean importing back the other way.

Nothing here imports `vespa_feeder`, which is what keeps that one-directional.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class FailedDocument:
    doc_id: str
    error: str


@dataclass
class VespaFeedError:
    """Transport layer gave up — no HTTP response received for some records."""

    feeder_error_count: int  # feeder.error.count
    failed_documents: list[FailedDocument]


@dataclass
class VespaResponseError:
    """HTTP responses received but records still lost after exhausting retries."""

    ok_count: int  # feeder.ok.count
    operation_count: int  # feeder.operation.count
    throttled_count: int  # requests that got a 429 at some point
    other_http_error_count: int  # non-2xx responses other than 429, e.g. 5xx
    failed_documents: list[FailedDocument]


VespaError = VespaFeedError | VespaResponseError


class VespaFeedResponse(BaseModel):
    """Parses the JSON stats the `vespa feed` CLI prints to stdout."""

    model_config = ConfigDict(populate_by_name=True)

    feeder_operation_count: int = Field(alias="feeder.operation.count", default=0)
    feeder_ok_count: int = Field(alias="feeder.ok.count", default=0)
    feeder_error_count: int = Field(alias="feeder.error.count", default=0)
    # The CLI's own self-measured feed duration - comparing this against our
    # wall-clock time around the subprocess call isolates process spawn/init/
    # connection-setup overhead (ours - theirs) from actual transfer time.
    feeder_seconds: float = Field(alias="feeder.seconds", default=0.0)
    http_response_error_count: int = Field(alias="http.response.error.count", default=0)
    http_response_code_counts: dict[str, int] = Field(
        alias="http.response.code.counts", default_factory=dict
    )


@dataclass
class FeedResult:
    feed_paths: list[Path]
    input_count: int
    operation_count: int
    ok_count: int
    feeder_error_count: int  # transport-layer failures, no HTTP response received
    throttled_count: int  # requests that got a 429 at some point (may have retried ok)
    other_http_error_count: int  # non-2xx responses other than 429, e.g. 5xx
    errors: list[VespaError]


class BatchAbandoned(Exception):
    """
    The drain gave up waiting on a batch; the batch itself may still be running.

    Distinct from a plain `TimeoutError` so the drain cannot confuse its own
    bound with one raised *by* a batch - `materialise_s3_files` raises
    `TimeoutError`, and under `raise_on_failure=False` that comes back as a
    value rather than being raised, so today the two only stay apart by
    coincidence of Prefect's return convention.

    An abandoned batch's `vespa feed` child is terminated by the drain, but it
    may have written an unknown share of its records first, so its records are
    reported as unaccounted for rather than counted either way.
    """


class VespaFeederFailed(Exception):
    """Records were lost: `vespa feed` never recovered them, or a batch raised."""

    def __init__(
        self,
        message: str,
        failed_results: list[FeedResult],
        crashes: list[BaseException] | None = None,
    ) -> None:
        super().__init__(message)
        self.failed_results = failed_results
        self.crashes = crashes or []

    def __reduce__(self):
        """
        Without this, unpickling calls __init__ with `args`, which holds only the message

        Prefect pickles exceptions to persist a failed run.
        """
        return (self.__class__, (str(self), self.failed_results, self.crashes))
