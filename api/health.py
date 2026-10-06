"""Health probes for the search API."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from time import perf_counter
from typing import Literal

import requests
from fastapi import APIRouter, Response
from pydantic import BaseModel

from api.settings import settings
from search.engines import OrderBy, Pagination, VespaError
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
)
from search.engines.vespa_query.client import API_TIMEOUT
from search.log import get_logger

logger = get_logger(__name__)

PROBE_QUERY = "climate"
PROBE_PAGINATION = Pagination(page_token=1, page_size=5)
PROBE_ORDER_BY: list[OrderBy] = []


class ProbeResult(BaseModel):
    name: str
    healthy: bool
    duration_ms: int


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    probes: list[ProbeResult]


def probe_vespa() -> None:
    """Vespa's own health endpoint - the discriminator between us and them."""
    response = requests.get(
        f"{settings.vespa_endpoint}/state/v1/health",
        timeout=API_TIMEOUT,
        headers={"Authorization": f"Bearer {settings.vespa_read_token}"},
    )
    if response.status_code != HTTPStatus.OK:
        raise VespaError(
            f"Vespa returned status {response.status_code} [health.vespa]",
            status_code=response.status_code,
        )
    code = response.json().get("status", {}).get("code")
    if code != "up":
        raise VespaError(
            f"Vespa reported status {code!r} [health.vespa]",
            status_code=response.status_code,
        )


def probe_documents_search() -> None:
    DevVespaDocumentSearchEngine(settings=settings).search(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )


def probe_documents_get() -> None:
    """
    Fetch a document by id, via the top hit rather than a pinned id.

    The id comes from a search so the probe cannot go red because one hard-coded
    document was unpublished - that is a corpus change, not a service failure.
    """
    engine = DevVespaDocumentSearchEngine(settings=settings)
    results = engine.search(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )
    if not results.results:
        raise VespaError(
            "No document matched, so document-by-id could not be checked "
            "[health.documents.get]",
            status_code=None,
        )
    if engine.get(results.results[0].id) is None:
        raise VespaError(
            "Vespa returned status 404 for a document it had just returned as a "
            "hit [health.documents.get]",
            status_code=HTTPStatus.NOT_FOUND,
        )


def probe_labels_search() -> None:
    DevVespaLabelSearchEngine(settings=settings).search(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )


def probe_passages_search() -> None:
    DevVespaPassageSearchEngine(settings=settings).search(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )


# A probe raises on failure and returns on success. Anything that is not a 2xx
# from Vespa already raises `VespaError` on the way up.
Probe = Callable[[], None]

PROBES: dict[str, Probe] = {
    "vespa": probe_vespa,
    "documents.search": probe_documents_search,
    "documents.get": probe_documents_get,
    "labels.search": probe_labels_search,
    "passages.search": probe_passages_search,
}

router = APIRouter(prefix="/health", tags=["health"])


def run_probe(name: str, probe: Probe) -> ProbeResult:
    """Run one probe and turn its outcome into a result row."""
    started = perf_counter()
    healthy = True
    # As a failure here is data over an actual fault, it is OK to swallow the exception:
    # one dead probe must not hide the other four. Why it failed is in the log.
    try:
        probe()
    except Exception:
        logger.exception(f"Error: health probe failed (probe={name})")
        healthy = False
    return ProbeResult(
        name=name,
        healthy=healthy,
        duration_ms=int((perf_counter() - started) * 1000),
    )


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health Check",
    responses={
        HTTPStatus.SERVICE_UNAVAILABLE: {"description": "At least one probe failed."}
    },
)
def read_health(response: Response) -> HealthResponse:
    """Run every probe concurrently and report each one."""
    with ThreadPoolExecutor(max_workers=len(PROBES)) as pool:
        futures = {
            name: pool.submit(run_probe, name, probe) for name, probe in PROBES.items()
        }
    # `run_probe` never raises, so every future has a result.
    probes = [futures[name].result() for name in PROBES]

    healthy = all(probe.healthy for probe in probes)
    response.status_code = HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
    return HealthResponse(
        status="healthy" if healthy else "unhealthy",
        probes=probes,
    )
