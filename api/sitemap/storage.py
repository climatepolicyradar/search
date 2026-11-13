from datetime import datetime
from typing import Annotated, Any

import httpx2
from pydantic import BeforeValidator, Field

from search.engines.vespa_query.client import Settings, aexecute_vespa_query
from search.engines.vespa_query.filters import (
    Filter,
    build_filter_query,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)
from search.engines.vespa_query.response import ByNameModel, VespaHit, VespaResponse


def _to_none(value: str) -> str | None:
    return value or None

VespaDateTime = Annotated[
    datetime | None,
    BeforeValidator(_to_none),
]

class SitemapDocument(ByNameModel):
    slug: str = Field(default="", validation_alias="deprecated_slug")
    last_updated_date: VespaDateTime = None


class SitemapStorage:
    def __init__(self, settings: Settings, httpx: httpx2.AsyncClient) -> None:
        self.settings = settings
        self._httpx = httpx

    async def documents(self, filters: Filter | None) -> list[SitemapDocument]:
        """List every document that has a slug a sitemap can link to."""
        where = 'true and deprecated_slug matches "."'
        where += build_filter_query(
            filters,
            field_map=documents_filter_field_to_vespa_field_map,
            struct_map=documents_filter_struct_field_to_vespa_field_map,
        )

        request_body: dict[str, Any] = {
            "yql": f"select * from sources documents where {where}",
            "presentation.summary": "sitemap",
            "ranking.profile": "unranked",
            "timeout": "5s",
            "hits": 50_000,
        }

        response = VespaResponse[VespaHit[SitemapDocument]].model_validate(
            await aexecute_vespa_query(
                endpoint=f"{self.settings.vespa_endpoint}/search",
                token=self.settings.vespa_read_token,
                request_context="sitemap.documents",
                request_body=request_body,
                client=self._httpx,
            )
        )

        response.root.raise_if_errors("sitemap.documents")
        hits = response.root.children or []
        return [hit.fields for hit in hits if hit.fields.slug]
