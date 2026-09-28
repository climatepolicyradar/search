"""HTTP execution against the Vespa query endpoint, with logging and error handling."""

from __future__ import annotations

import json
import time
from typing import Any

import requests
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

from search.engines import VespaError
from search.log import get_logger

logger = get_logger(__name__)

API_TIMEOUT = 5  # seconds
HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS = 512


class Settings(BaseSettings):
    vespa_endpoint: AnyHttpUrl
    vespa_read_token: str
    vespa_dev_instance_name: str | None = (
        None  # personal dev instance; None == full/prod
    )


def _get_total_count(response: dict[str, Any]) -> int | None:
    return response.get("root", {}).get("fields", {}).get("totalCount")


def _warn_if_degraded(response_json: dict[str, Any], request_context: str) -> None:
    """
    Warn when Vespa answered from less than the whole corpus.

    A query that exhausts its budget, or whose content nodes did not all answer,
    comes back as a 200 carrying partial results. That is a valid response - it is
    not an error and must not be raised - but the hits are drawn from a subset of
    the corpus, so ranking comparisons built on it are not comparable with a full
    one. WARNING because the caller still gets a usable answer.

    @see: https://docs.vespa.ai/en/performance/graceful-degradation.html
    """
    coverage = response_json.get("root", {}).get("coverage") or {}
    # Vespa reports every degradation reason it knows about, most of them false.
    reasons = {
        reason: value
        for reason, value in (coverage.get("degraded") or {}).items()
        if value
    }
    covered_percent = coverage.get("coverage")
    incomplete = isinstance(covered_percent, (int, float)) and covered_percent < 100
    if not reasons and not incomplete:
        return

    logger.warning(
        "Vespa returned a degraded result [%s] (coverage=%s%%, documents=%s, "
        "degraded=%s)",
        request_context,
        covered_percent,
        coverage.get("documents"),
        reasons or None,
    )


def _execute_vespa_query(
    *,
    endpoint: str,
    token: str,
    request_body: dict[str, Any],
    request_context: str,
    post_fn=requests.post,
) -> dict[str, Any]:
    """
    Execute a Vespa query and emit contextual logs.

    :param endpoint: Fully-qualified Vespa query endpoint URL.
    :type endpoint: str
    :param token: Bearer token used for read access.
    :type token: str
    :param request_body: JSON payload sent to Vespa.
    :type request_body: dict[str, Any]
    :param request_context: Context label for logs.
    :type request_context: str
    :param post_fn: HTTP post callable for dependency injection in tests.
    :type post_fn: typing.Callable[..., requests.Response]
    :return: Decoded JSON response.
    :rtype: dict[str, Any]
    :raises VespaError: if the request never reached Vespa, Vespa returned a
        non-success status, or the response body was not JSON.

    Failures are raised, never returned as an empty result. "Vespa is broken"
    and "nothing matched your query" are different answers, and a caller that
    collapses the first into the second leaves clients unable to tell them
    apart. The return type is deliberately non-optional so that regressing to
    ``return None`` here fails type checking.
    """
    request_body = {"presentation.timing": True, **request_body}

    logger.info("Vespa request started [%s]", request_context)
    logger.debug(
        "Vespa request payload [%s]: %s",
        request_context,
        json.dumps(request_body, indent=2),
    )

    started = time.perf_counter()
    try:
        response = post_fn(
            endpoint,
            json=request_body,
            timeout=API_TIMEOUT,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
    except Exception as exc:
        logger.exception(
            "Error: Vespa request failed before a response was received [%s] "
            "(elapsed_ms=%d)",
            request_context,
            (time.perf_counter() - started) * 1000,
        )
        raise VespaError(
            f"Vespa request failed before a response was received [{request_context}]"
        ) from exc

    if response.status_code >= 400:
        body_preview = (response.text or "")[:HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS]
        logger.error(
            "Error: Vespa returned a non-success status code [%s] "
            "(status=%s, body_preview=%r)",
            request_context,
            response.status_code,
            body_preview,
        )
        raise VespaError(
            f"Vespa returned status {response.status_code} [{request_context}]: "
            f"{body_preview}"
        )

    try:
        response_json = response.json()
    except ValueError as exc:
        logger.exception("Error: Vespa returned invalid JSON [%s]", request_context)
        raise VespaError(f"Vespa returned invalid JSON [{request_context}]") from exc

    _warn_if_degraded(response_json, request_context)

    hit_count = len(response_json.get("root", {}).get("children", []) or [])
    timing = response_json.get("timing") or {}
    logger.info(
        "Success: Vespa request completed [%s] (hits=%s, total_count=%s, "
        "elapsed_ms=%d, vespa_querytime_ms=%d, vespa_summaryfetchtime_ms=%d, "
        "vespa_searchtime_ms=%d, bytes=%d, summary=%s)",
        request_context,
        hit_count,
        _get_total_count(response_json),
        (time.perf_counter() - started) * 1000,
        timing.get("querytime", 0) * 1000,
        timing.get("summaryfetchtime", 0) * 1000,
        timing.get("searchtime", 0) * 1000,
        len(response.content),
        request_body.get("presentation.summary", "default"),
    )
    return response_json
