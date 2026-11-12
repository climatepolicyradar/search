from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from opentelemetry import trace

from api.taxonomy.models import (
    LabelNode,
    TaxonomyNode,
    merge,
    select,
    taxonomy,
    tree,
)
from search.engines.dev_vespa.documents_search_engine import DocumentSearchEngine
from search.engines.dev_vespa.labels_search_engine import LabelSearchEngine
from search.engines.vespa_query.filters import Filter

tracer = trace.get_tracer(__name__)


class TaxonomyNotLoadedError(Exception):
    def __init__(self) -> None:
        super().__init__("The taxonomy has not been fetched from Vespa yet")


@dataclass
class Loaded:
    roots: list[LabelNode]
    fetched_at: datetime


class TaxonomyService:
    def __init__(
        self,
        labels: LabelSearchEngine,
        documents: DocumentSearchEngine,
    ) -> None:
        self._loaded: Loaded | None = None
        self._labels = labels
        self._documents = documents

    def roots(self) -> list[LabelNode]:
        """Return the roots of the current taxonomy forest."""
        if self._loaded is None:
            raise TaxonomyNotLoadedError()

        age = datetime.now(UTC) - self._loaded.fetched_at
        trace.get_current_span().set_attribute("taxonomy.age_seconds", age.total_seconds())
        return self._loaded.roots

    async def nodes(
        self,
        query: str | None,
        filters: Filter | None,
        label_types: list[str] | None,
        label_ids: list[str] | None,
        msm: float,
    ) -> list[TaxonomyNode]:
        """Return the requested label subtrees, counted over the documents `query` and `filters` match."""
        selected = select(self.roots(), label_types, label_ids)
        taxonomy_types = sorted({type for node in selected for type in node.types()})
        counts = await self._documents.label_counts(query, filters, taxonomy_types, msm)
        return [node.response(counts) for node in selected]

    async def _refresh(self) -> None:
        with tracer.start_as_current_span("taxonomy.refresh") as span:
            fetched = await self._labels.all_labels()
            loaded = Loaded(
                roots=tree(merge(taxonomy, fetched)),
                fetched_at=datetime.now(UTC),
            )
            self._loaded = loaded
            span.set_attribute("taxonomy.labels", len(fetched))
            span.set_attribute("taxonomy.roots", len(loaded.roots))

    async def _poll_once(self) -> None:
        with suppress(Exception):
            await self._refresh()

    async def _poll(self) -> None:
        while True:
            await self._poll_once()
            await asyncio.sleep(delay = 3600)

    @asynccontextmanager
    async def run(self) -> AsyncGenerator[None, None]:
        """Poll for the taxonomy for as long as the context is open."""
        task = asyncio.create_task(self._poll())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
