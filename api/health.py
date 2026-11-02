"""Health probes for the search API."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from http import HTTPStatus
from time import perf_counter
from typing import Annotated, Literal

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from api.settings import settings
from api.state import HttpxDep
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


async def probe_vespa(client: httpx2.AsyncClient) -> None:
    """Vespa's own health endpoint - the discriminator between us and them."""
    headers = (
        {"Authorization": f"Bearer {settings.vespa_read_token}"}
        if settings.vespa_read_token
        else {}
    )
    response = await client.get(
        f"{settings.vespa_endpoint}/state/v1/health",
        timeout=API_TIMEOUT,
        headers=headers,
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


async def probe_documents_search() -> None:
    await DevVespaDocumentSearchEngine(settings=settings).asearch(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )


async def probe_documents_get() -> None:
    """
    Fetch a document by id, via the top hit rather than a pinned id.

    The id comes from a search so the probe cannot go red because one hard-coded
    document was unpublished - that is a corpus change, not a service failure.
    """
    engine = DevVespaDocumentSearchEngine(settings=settings)
    results = await engine.asearch(
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
    if await engine.aget(results.results[0].id) is None:
        raise VespaError(
            "Vespa returned status 404 for a document it had just returned as a "
            "hit [health.documents.get]",
            status_code=HTTPStatus.NOT_FOUND,
        )


async def probe_labels_search() -> None:
    await DevVespaLabelSearchEngine(settings=settings).asearch(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )


async def probe_passages_search(client: httpx2.AsyncClient) -> None:
    await DevVespaPassageSearchEngine(settings=settings, httpx=client).asearch(
        query=PROBE_QUERY,
        pagination=PROBE_PAGINATION,
        order_by=PROBE_ORDER_BY,
    )


# A probe raises on failure and returns on success. Anything that is not a 2xx
# from Vespa already raises `VespaError` on the way up.
Probe = Callable[[], Awaitable[None]]


def probes(http: HttpxDep) -> dict[str, Probe]:
    return {
        "vespa": partial(probe_vespa, http),
        "documents.search": probe_documents_search,
        "documents.get": probe_documents_get,
        "labels.search": probe_labels_search,
        "passages.search": partial(probe_passages_search, http),
    }


ProbesDep = Annotated[dict[str, Probe], Depends(probes)]

router = APIRouter(prefix="/health", tags=["health"])


async def run_probe(name: str, probe: Probe) -> ProbeResult:
    """Run one probe and turn its outcome into a result row."""
    started = perf_counter()
    healthy = True
    # As a failure here is data over an actual fault, it is OK to swallow the exception:
    # one dead probe must not hide the other four. Why it failed is in the log.
    try:
        await probe()
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
async def read_health(response: Response, probes: ProbesDep) -> HealthResponse:
    """Run every probe concurrently and report each one."""
    results = await asyncio.gather(
        *(run_probe(name, probe) for name, probe in probes.items())
    )

    healthy = all(result.healthy for result in results)
    response.status_code = HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
    return HealthResponse(
        status="healthy" if healthy else "unhealthy",
        probes=results,
    )


@router.get(
    "/probes/{probe_id}",
    response_model=ProbeResult,
    summary="Health Check: One Probe",
    responses={
        HTTPStatus.NOT_FOUND: {"description": "No probe goes by that name."},
        HTTPStatus.SERVICE_UNAVAILABLE: {"description": "The probe failed."},
    },
)
async def read_probe(
    probe_id: str,
    response: Response,
    probes: ProbesDep,
) -> ProbeResult:
    """Run one probe used in our canaries in ./observability."""
    probe = probes.get(probe_id)
    if probe is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Unknown probe {probe_id!r}. Available: {', '.join(probes)}",
        )
    result = await run_probe(probe_id, probe)
    response.status_code = (
        HTTPStatus.OK if result.healthy else HTTPStatus.SERVICE_UNAVAILABLE
    )
    return result
