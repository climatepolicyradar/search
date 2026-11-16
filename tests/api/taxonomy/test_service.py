import asyncio

import pytest

from api.taxonomy.service import TaxonomyNotLoadedError, TaxonomyService
from search.engines import VespaError
from search.label import LabelSearchResult
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)
from tests.engines.dev_vespa.stub_labels_search_engine import StubLabelSearchEngine

KEYWORD = LabelSearchResult.model_validate(
    {
        "id": "keyword::Flood",
        "type": "keyword",
        "value": "Flood",
        "labels": [],
        "alternative_labels": ["Flooding"],
    }
)

VESPA_DOWN = VespaError("Vespa is down", status_code=None)


def _service(stub: StubLabelSearchEngine) -> TaxonomyService:
    return TaxonomyService(
        labels=stub,
        documents=StubDocumentSearchEngine(),
    )


async def _wait_for_fetch(stub: StubLabelSearchEngine, calls: int = 1) -> None:
    async with asyncio.timeout(1):
        while stub.all_labels_calls < calls:
            await asyncio.sleep(0)


def test_roots_raises_before_the_first_fetch() -> None:
    with pytest.raises(TaxonomyNotLoadedError):
        _service(StubLabelSearchEngine()).roots()


async def test_roots_returns_the_fetched_labels() -> None:
    stub = StubLabelSearchEngine()
    stub.add_all_labels_response([KEYWORD])
    service = _service(stub)

    await service._refresh()

    assert "keyword::Flood" in {root.id for root in service.roots()}


async def test_the_hardcoded_taxonomy_is_merged_in() -> None:
    stub = StubLabelSearchEngine()
    stub.add_all_labels_response([])
    service = _service(stub)

    await service._refresh()

    assert service.roots() != []


async def test_a_failed_refresh_keeps_the_last_good_taxonomy() -> None:
    stub = StubLabelSearchEngine()
    stub.add_all_labels_response([KEYWORD])
    stub.add_all_labels_response(VESPA_DOWN)
    service = _service(stub)
    await service._refresh()
    before = service.roots()

    await service._poll_once()

    assert service.roots() is before


async def test_a_failed_first_refresh_leaves_the_taxonomy_unloaded() -> None:
    stub = StubLabelSearchEngine()
    stub.add_all_labels_response(VESPA_DOWN)
    service = _service(stub)

    await service._poll_once()

    with pytest.raises(TaxonomyNotLoadedError):
        service.roots()


async def test_an_unexpected_failure_does_not_escape_the_poller() -> None:
    service = _service(StubLabelSearchEngine())

    await service._poll_once()

    with pytest.raises(TaxonomyNotLoadedError):
        service.roots()


async def test_run_fetches_in_the_background() -> None:
    stub = StubLabelSearchEngine()
    stub.add_all_labels_response([KEYWORD])
    service = _service(stub)

    async with service.run():
        await _wait_for_fetch(stub)

    assert "keyword::Flood" in {root.id for root in service.roots()}
