from api.sitemap.storage import SitemapDocument
from search.engines import VespaError
from search.engines.vespa_query.filters import Filter


class StubSitemapStorage:
    def __init__(self) -> None:
        self.requested_filters: list[Filter | None] = []
        self._responses: list[list[SitemapDocument] | VespaError] = []

    def add_response(self, response: list[SitemapDocument] | VespaError) -> None:
        self._responses.append(response)

    async def documents(self, filters: Filter | None) -> list[SitemapDocument]:
        self.requested_filters.append(filters)
        match self._responses.pop(0):
            case VespaError() as error:
                raise error
            case response:
                return response
