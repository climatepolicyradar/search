import json
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.sitemap.deps import _sitemap_storage
from api.sitemap.storage import SitemapDocument
from search.engines import VespaError
from tests.api.sitemap.stub_sitemap_storage import StubSitemapStorage
from tests.conftest import override_dependency

_URL = "/search/documents:sitemap"


@pytest.fixture
def storage(app: FastAPI) -> Generator[StubSitemapStorage]:
    yield from override_dependency(
        app=app,
        key=_sitemap_storage,
        value=StubSitemapStorage(),
    )


def test_lists_slugs_and_dates(storage: StubSitemapStorage, test_client: TestClient) -> None:
    updated = datetime(2021, 3, 5, tzinfo=UTC)
    storage.add_response([SitemapDocument(slug="a-slug", last_updated_date=updated)])
    response = test_client.get(_URL)

    assert response.json() == {
        "data": [
            {"slug": "a-slug", "last_updated_date": "2021-03-05T00:00:00Z"}
        ]
    }


def test_a_document_without_a_date_still_gets_a_url(
    storage: StubSitemapStorage,
    test_client: TestClient,
) -> None:
    storage.add_response([SitemapDocument(slug="a-slug", last_updated_date=None)])
    response = test_client.get(_URL)

    assert response.json()["data"][0]["last_updated_date"] is None


def test_passes_filters_through(storage: StubSitemapStorage, test_client: TestClient) -> None:
    filters = {
        "op": "and",
        "filters": [
            {"field": "labels.value.id", "op": "contains", "value": "status::Principal"}
        ],
    }
    storage.add_response([])
    test_client.get(_URL, params={"filters": json.dumps(filters)})

    assert storage.requested_filters[0] is not None


def test_malformed_filters_are_rejected(
    storage: StubSitemapStorage,
    test_client: TestClient,
) -> None:
    response = test_client.get(_URL, params={"filters": "not json"})

    assert response.status_code == 400


def test_an_unreachable_vespa_is_a_503(
    storage: StubSitemapStorage,
    test_client: TestClient,
) -> None:
    storage.add_response(VespaError("connect timed out to vespa-app.cloud", status_code=None))
    response = test_client.get(_URL)

    assert response.status_code == 503


def test_a_throttled_query_is_a_429(
    storage: StubSitemapStorage,
    test_client: TestClient,
) -> None:
    storage.add_response(VespaError("too many requests", status_code=429))
    response = test_client.get(_URL)

    assert response.status_code == 429


def test_the_error_body_does_not_leak_the_vespa_message(
    storage: StubSitemapStorage,
    test_client: TestClient,
) -> None:
    storage.add_response(VespaError("select * from documents where secret", status_code=500))
    response = test_client.get(_URL)

    assert "secret" not in response.text
