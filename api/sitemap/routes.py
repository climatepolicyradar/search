from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, HTTPException

from api.errors import vespa_error_status
from api.filters import DocumentsFilterDep
from api.models import ItemResponse
from api.responses import SEARCH_RESPONSES
from api.sitemap.deps import SitemapStorageDep
from api.sitemap.storage import SitemapDocument
from search.engines import VespaError

SITEMAP_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.BAD_REQUEST: {"description": "Malformed `filters` JSON."},
    **SEARCH_RESPONSES,
}

router = APIRouter(tags=["sitemap"])


@router.get(
    "/documents:sitemap",
    response_model=ItemResponse[list[SitemapDocument]],
    responses=SITEMAP_RESPONSES,
)
async def read_sitemap(
    filters: DocumentsFilterDep,
    storage: SitemapStorageDep,
) -> ItemResponse[list[SitemapDocument]]:
    """Lists every matching document's slug and last-updated date, unpaginated."""
    try:
        return ItemResponse(data=await storage.documents(filters))
    except VespaError as error:
        raise HTTPException(
            status_code=vespa_error_status(error),
            detail="Could not list documents for the sitemap.",
        ) from error
