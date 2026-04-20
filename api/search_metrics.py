"""Search metrics helpers for the search API."""

from enum import StrEnum
from time import perf_counter

from api.observability.src.api import MetricsService

MS_PER_SECOND = 1000
LATENCY_PRECISION_DECIMALS = 2
DEFAULT_HTTP_ERROR_STATUS_CODE = 500
REQUEST_DURATION_METRIC_NAME = "http_request_duration_seconds"
REQUEST_DURATION_METRIC_DESCRIPTION = "Duration of HTTP requests handled by search API."
REQUEST_DURATION_METRIC_UNIT = "s"
METRIC_ATTR_METHOD = "http.request.method"
METRIC_ATTR_PATH = "http.route"
METRIC_ATTR_STATUS_CODE = "http.response.status_code"
METRIC_ATTR_OUTCOME = "http.request.outcome"


class Outcome(StrEnum):
    SUCCESS = "success"
    REDIRECT = "redirect"
    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"
    EXCEPTION = "exception"
    UNKNOWN = "unknown"


class SearchMetrics:
    """Record per-request duration metrics for FastAPI handlers."""

    def __init__(self, metrics_service: MetricsService) -> None:
        """
        Initialise request metrics instruments.

        :param metrics_service: Shared metrics service wrapper.
        :type metrics_service: MetricsService
        """
        self._request_duration_histogram = metrics_service.create_histogram(
            name=REQUEST_DURATION_METRIC_NAME,
            description=REQUEST_DURATION_METRIC_DESCRIPTION,
            unit=REQUEST_DURATION_METRIC_UNIT,
        )

    @staticmethod
    def elapsed_ms(start_time: float) -> float:
        """
        Return elapsed milliseconds for a start time.

        :param start_time: Monotonic start time from ``perf_counter()``.
        :type start_time: float
        :return: Elapsed duration in milliseconds.
        :rtype: float
        """
        return round(
            (perf_counter() - start_time) * MS_PER_SECOND,
            LATENCY_PRECISION_DECIMALS,
        )

    def record_success(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """
        Record successful request duration metrics.

        :param method: HTTP method (e.g. ``GET``).
        :type method: str
        :param path: Request path.
        :type path: str
        :param status_code: HTTP response status code.
        :type status_code: int
        :param duration_ms: Request duration in milliseconds.
        :type duration_ms: float
        """
        self._record(
            method=method,
            path=self.normalise_path(path),
            status_code=status_code,
            outcome=self.outcome_for_status_code(status_code),
            duration_ms=duration_ms,
        )

    def record_error(
        self,
        *,
        method: str,
        path: str,
        duration_ms: float,
        status_code: int = DEFAULT_HTTP_ERROR_STATUS_CODE,
    ) -> None:
        """
        Record failed request duration metrics.

        :param method: HTTP method (e.g. ``GET``).
        :type method: str
        :param path: Request path.
        :type path: str
        :param duration_ms: Request duration in milliseconds.
        :type duration_ms: float
        :param status_code: Status code to record for unhandled failures.
        :type status_code: int
        """
        self._record(
            method=method,
            path=self.normalise_path(path),
            status_code=status_code,
            outcome=Outcome.EXCEPTION,
            duration_ms=duration_ms,
        )

    @staticmethod
    def normalise_path(path: str) -> str:
        """
        Return a bounded-cardinality path label.

        This strips query strings and ensures a deterministic fallback value.

        :param path: Raw request path or route template.
        :type path: str
        :return: Canonical path label.
        :rtype: str
        """
        if not path:
            return "/unknown"

        path_without_query = path.split("?", maxsplit=1)[0] or "/unknown"
        return path_without_query

    @staticmethod
    def outcome_for_status_code(status_code: int) -> Outcome:
        """
        Return a finite outcome taxonomy derived from status code.

        :param status_code: HTTP status code.
        :type status_code: int
        :return: One of the defined metric outcome categories.
        :rtype: Outcome
        """
        if 200 <= status_code <= 299:
            return Outcome.SUCCESS
        if 300 <= status_code <= 399:
            return Outcome.REDIRECT
        if 400 <= status_code <= 499:
            return Outcome.CLIENT_ERROR
        if 500 <= status_code <= 599:
            return Outcome.SERVER_ERROR
        return Outcome.UNKNOWN

    def _record(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        outcome: Outcome,
        duration_ms: float,
    ) -> None:
        """
        Record duration measurement if histogram instrument exists.

        :param method: HTTP method.
        :type method: str
        :param path: Request path.
        :type path: str
        :param status_code: HTTP response status code.
        :type status_code: int
        :param outcome: Outcome enum for aggregation labels.
        :type outcome: Outcome
        :param duration_ms: Duration in milliseconds.
        :type duration_ms: float
        """
        if self._request_duration_histogram is None:
            return

        duration_seconds = duration_ms / MS_PER_SECOND
        self._request_duration_histogram.record(
            duration_seconds,
            attributes={
                METRIC_ATTR_METHOD: method,
                METRIC_ATTR_PATH: path,
                METRIC_ATTR_STATUS_CODE: status_code,
                METRIC_ATTR_OUTCOME: outcome.value,
            },
        )
