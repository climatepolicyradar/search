from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx2

from api.state import State
from api.taxonomy.service import TaxonomyService
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)
from tests.engines.dev_vespa.stub_labels_search_engine import StubLabelSearchEngine


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

    yield State(
        httpx=httpx,
        labels=labels,
        documents=documents,
        taxonomy=taxonomy,
    )
