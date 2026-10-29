"""E2E tests for ``GET /search/geographies:aggregate`` against a real Vespa."""

from http import HTTPStatus
from typing import Any

import pytest
import requests as req
from cpr_contracts import Document, DocumentLabelRelationship, Label
from fastapi.testclient import TestClient
from polyfactory.factories.pydantic_factory import ModelFactory
from vespa.application import Vespa

from api.main import app
from search.vespa.documents_feed_materializer import _source_document_to_vespa_update
from tests.vespa_e2e import _TEST_SETTINGS

pytest_plugins = ["tests.vespa_e2e"]


class LabelRelationshipFactory(ModelFactory[DocumentLabelRelationship]):
    @classmethod
    def build(
        cls, factory_use_construct: bool = False, **kwargs: Any
    ) -> DocumentLabelRelationship:
        kwargs.setdefault("timestamp", None)
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


class DocumentFactory(ModelFactory[Document]):
    @classmethod
    def build(cls, factory_use_construct: bool = False, **kwargs: Any) -> Document:
        if "labels" not in kwargs:
            kwargs["labels"] = [
                LabelRelationshipFactory.build(
                    factory_use_construct=factory_use_construct
                )
            ]
        if "documents" not in kwargs:
            kwargs["documents"] = []
        return super().build(factory_use_construct=factory_use_construct, **kwargs)


def _label(label_id: str, value: str, label_type: str) -> DocumentLabelRelationship:
    return DocumentLabelRelationship(
        type=label_type,
        value=Label(id=label_id, value=value, type=label_type, labels=[]),
        timestamp=None,
    )


def _feed_document(vespa_app: Vespa, document: Document) -> None:
    op = _source_document_to_vespa_update(document)
    r = req.put(
        f"{vespa_app.end_point}/document/v1/documents/documents/docid/{document.id}",
        json={**op, "create": True},  # type: ignore[arg-type]
        timeout=5,
    )
    r.raise_for_status()


@pytest.fixture
def api_client(vespa_app: Vespa, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient whose routes talk to the e2e Vespa rather than a mock."""
    monkeypatch.setattr("api.routers.settings", _TEST_SETTINGS)
    return TestClient(app)


def test_aggregate_geographies_returns_real_counts_for_fed_documents(
    api_client: TestClient, vespa_app: Vespa
) -> None:
    """
    The whole path: HTTP -> YQL grouping -> Vespa -> response.

    Two documents share a country, so the count must be 2 rather than two
    groups of 1 -- the thing a mocked engine cannot tell us.
    """
    shared = "country::E2E-AGG-AUS"
    doc_1 = DocumentFactory.build(labels=[_label(shared, "Australia", "country")])
    doc_2 = DocumentFactory.build(labels=[_label(shared, "Australia", "country")])
    _feed_document(vespa_app, doc_1)
    _feed_document(vespa_app, doc_2)

    response = api_client.get("/search/geographies:aggregate")

    assert response.status_code == HTTPStatus.OK
    counts = {a["value"]["id"]: a["count"] for a in response.json()["data"]}
    assert counts.get(shared) == 2


def test_aggregate_geographies_excludes_non_geography_labels_from_real_data(
    api_client: TestClient, vespa_app: Vespa
) -> None:
    """The type whitelist holds against the label types Vespa really returns."""
    doc = DocumentFactory.build(
        labels=[
            _label("country::E2E-AGG-FRA", "France", "country"),
            _label("category::E2E-AGG-Law", "Law", "category"),
        ]
    )
    _feed_document(vespa_app, doc)

    response = api_client.get("/search/geographies:aggregate")

    assert response.status_code == HTTPStatus.OK
    data = response.json()["data"]
    returned_ids = {a["value"]["id"] for a in data}
    assert "country::E2E-AGG-FRA" in returned_ids
    assert "category::E2E-AGG-Law" not in returned_ids
    assert {a["value"]["type"] for a in data} <= {"region", "country", "subdivision"}


def test_aggregate_geographies_default_includes_every_geography_type(
    api_client: TestClient, vespa_app: Vespa
) -> None:
    """
    With no type given, all three geography types must come back.

    The default is the `GeographyType` literal, so a type dropped from it
    disappears from the endpoint silently -- this pins all three.
    """
    doc = DocumentFactory.build(
        labels=[
            _label("region::E2E-AGG-DEFAULT-oceania", "Oceania", "region"),
            _label("country::E2E-AGG-DEFAULT-AUS", "Australia", "country"),
            _label("subdivision::E2E-AGG-DEFAULT-AU-NSW", "New South Wales", "subdivision"),
        ]
    )
    _feed_document(vespa_app, doc)

    response = api_client.get("/search/geographies:aggregate")

    assert response.status_code == HTTPStatus.OK
    returned_ids = {a["value"]["id"] for a in response.json()["data"]}
    assert "region::E2E-AGG-DEFAULT-oceania" in returned_ids
    assert "country::E2E-AGG-DEFAULT-AUS" in returned_ids
    assert "subdivision::E2E-AGG-DEFAULT-AU-NSW" in returned_ids


def test_aggregate_geographies_rejects_unknown_type(
    api_client: TestClient, vespa_app: Vespa
) -> None:
    """An unknown type is a 422 from the literal, not an empty result set."""
    response = api_client.get(
        "/search/geographies:aggregate",
        params={"labels.value.type": "planet"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_aggregate_geographies_counts_respect_the_filters(
    api_client: TestClient, vespa_app: Vespa
) -> None:
    """
    The endpoint's contract is that it scopes to the same set as /documents.

    A filter that excludes a document must drop it from the counts, which is
    what makes the filter UI's options agree with its results (FUS-475).
    """
    inside = DocumentFactory.build(
        labels=[
            _label("country::E2E-AGG-KEN", "Kenya", "country"),
            _label("category::E2E-AGG-Inside", "Inside", "category"),
        ]
    )
    outside = DocumentFactory.build(
        labels=[
            _label("country::E2E-AGG-KEN", "Kenya", "country"),
            _label("category::E2E-AGG-Outside", "Outside", "category"),
        ]
    )
    _feed_document(vespa_app, inside)
    _feed_document(vespa_app, outside)

    filters = (
        '{"op":"and","filters":[{"field":"labels.value.id","op":"contains",'
        '"value":"category::E2E-AGG-Inside"}]}'
    )
    response = api_client.get(
        "/search/geographies:aggregate", params={"filters": filters}
    )

    assert response.status_code == HTTPStatus.OK
    counts = {a["value"]["id"]: a["count"] for a in response.json()["data"]}
    assert counts.get("country::E2E-AGG-KEN") == 1


def test_aggregate_geographies_type_filter_against_real_data(
    api_client: TestClient, vespa_app: Vespa
) -> None:
    """`labels.value.type` narrows real Vespa groups, not a hand-built list."""
    doc = DocumentFactory.build(
        labels=[
            _label("country::E2E-AGG-BRA", "Brazil", "country"),
            _label("subdivision::E2E-AGG-BR-SP", "Sao Paulo", "subdivision"),
        ]
    )
    _feed_document(vespa_app, doc)

    response = api_client.get(
        "/search/geographies:aggregate",
        params={"labels.value.type": "subdivision"},
    )

    assert response.status_code == HTTPStatus.OK
    returned_ids = {a["value"]["id"] for a in response.json()["data"]}
    assert "subdivision::E2E-AGG-BR-SP" in returned_ids
    assert "country::E2E-AGG-BRA" not in returned_ids
