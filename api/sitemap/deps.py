from typing import Annotated

from fastapi import Depends

from api.sitemap.storage import SitemapStorage
from api.state import StateDep


def _sitemap_storage(state: StateDep) -> SitemapStorage:
    return state.sitemap


SitemapStorageDep = Annotated[
    SitemapStorage,
    Depends(_sitemap_storage),
]
