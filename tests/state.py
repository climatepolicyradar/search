from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx2
from pydantic import AnyHttpUrl

from api.sitemap.storage import SitemapStorage
from api.state import State
from api.taxonomy.service import TaxonomyService
from search.engines.vespa_query.client import Settings
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)
from tests.engines.dev_vespa.stub_labels_search_engine import StubLabelSearchEngine

TEST_SETTINGS = Settings(
    vespa_endpoint=AnyHttpUrl("http://localhost:8080"),
    vespa_read_token="test-read-token",  # nosec B106
)


@asynccontextmanager
async def stub_state(httpx: httpx2.AsyncClient) -> AsyncGenerator[State, None]:
    """
    Create a test mirror of all application dependencies.

    By default everything is stubbed, so e.g. service level tests should
    have their own fixture that creates a real instance backed by its deps.
    """
    labels = StubLabelSearchEngine()
    documents = StubDocumentSearchEngine()
    taxonomy =TaxonomyService(labels=labels, documents=documents)
    sitemap = SitemapStorage(settings=TEST_SETTINGS, httpx=httpx)

    yield State(
        httpx=httpx,
        labels=labels,
        documents=documents,
        taxonomy=taxonomy,
        sitemap=sitemap,
    )
