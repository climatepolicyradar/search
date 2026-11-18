import httpx2
import pytest

from api.sitemap.storage import SitemapDocument, SitemapStorage
from search.engines import VespaError
from search.engines.vespa_query.filters import FieldFilter, Filter
from tests.http import MockHandler
from tests.state import TEST_SETTINGS


def _hits(*fields: dict[str, str]) -> dict[str, object]:
    return {"root": {"children": [{"fields": field} for field in fields]}}


@pytest.fixture
def storage(http_client: httpx2.AsyncClient) -> SitemapStorage:
    return SitemapStorage(settings=TEST_SETTINGS, httpx=http_client)


async def test_requests_the_sitemap_summary(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    handler.add_response(_hits())
    await storage.documents(filters=None)
    assert handler.last_json()["presentation.summary"] == "sitemap"


async def test_asks_for_a_whole_sitemap_file_of_hits(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    handler.add_response(_hits())
    await storage.documents(filters=None)
    assert handler.last_json()["hits"] == 50_000


async def test_does_not_rank(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    handler.add_response(_hits())
    await storage.documents(filters=None)
    assert handler.last_json()["ranking.profile"] == "unranked"


async def test_excludes_documents_without_a_slug(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    handler.add_response(_hits())
    await storage.documents(filters=None)
    assert 'deprecated_slug matches "."' in handler.last_json()["yql"]


async def test_applies_the_callers_filters(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    principal = FieldFilter(field="labels.value.id", op="contains", value="status::Principal")
    filters = Filter(op="and", filters=[principal])
    handler.add_response(_hits())
    await storage.documents(filters=filters)
    assert 'labels.id contains "status::Principal"' in handler.last_json()["yql"]


async def test_reads_the_summary_fields(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    hit = {
        "deprecated_slug": "planning-act-2008-1e9d",
        "last_updated_date": "2021-03-05T00:00:00Z",
    }
    handler.add_response(_hits(hit))
    documents = await storage.documents(filters=None)

    assert documents == [SitemapDocument.model_validate(hit)]


async def test_an_unset_last_updated_date_reads_as_none(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    hit = {"deprecated_slug": "a-slug", "last_updated_date": ""}
    handler.add_response(_hits(hit))
    documents = await storage.documents(filters=None)

    assert documents[0].last_updated_date is None


async def test_errors_inside_a_200_are_raised(
    storage: SitemapStorage,
    handler: MockHandler,
) -> None:
    error = {"code": 8, "summary": "Backend communication error"}
    handler.add_response({"root": {"errors": [error]}})

    with pytest.raises(VespaError):
        await storage.documents(filters=None)
