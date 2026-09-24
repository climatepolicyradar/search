"""Tests for ``GET /search/documents/{document_id}``."""

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import API_TITLE, API_VERSION, app
from search.data_in_models import Document
from search.engines import ListResponse, VespaError


@pytest.fixture
def document_client():
    """Provide a test client with the document engine mocked."""
    with patch("api.routers.DevVespaDocumentSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine
        yield TestClient(app), mock_engine


def test_get_document_returns_200_when_found(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.get.return_value = Document(
        id="doc-1",
        title="A Climate Document",
        description="About climate.",
    )

    response = client.get("/search/documents/doc-1")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["data"]["id"] == "doc-1"
    mock_engine.get.assert_called_once_with("doc-1")


def test_get_document_returns_404_when_not_found(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.get.return_value = None

    response = client.get("/search/documents/missing-id")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_document_returns_503_on_vespa_error(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.get.side_effect = VespaError("Vespa is down")

    response = client.get("/search/documents/doc-1")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


def test_aggregations_are_omitted_unless_requested(document_client) -> None:
    """
    `aggregations.labels` is part of the read mask, not a freebie.

    The grouping is `max(5000)` over two grouping fields and dominates the
    response size, so a caller that does not ask for it must not pay for the
    query or receive the payload.
    """
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )

    response = client.get("/search/documents", params={"query": "toxic"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["aggregations"] is None
    mock_engine.aggregations.assert_not_called()


def test_aggregations_are_returned_when_requested(document_client) -> None:
    client, mock_engine = document_client
    mock_engine.search.return_value = ListResponse(
        results=[], total_size=0, next_page_token=None
    )
    # An empty aggregation set is a legitimate result, and must still be
    # reported as `[]` rather than collapsing back into "not requested".
    mock_engine.aggregations.return_value = []

    response = client.get(
        "/search/documents",
        params={"query": "toxic", "fields": "aggregations.labels"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["aggregations"] == {"labels": []}
    mock_engine.aggregations.assert_called_once()


def test_an_unknown_field_is_rejected(document_client) -> None:
    client, _ = document_client

    response = client.get(
        "/search/documents", params={"query": "toxic", "fields": "not.a.field"}
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_labels_taxonomy_returns_non_empty_list() -> None:
    client = TestClient(app)

    response = client.get("/search/labels-taxonomy")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total_size"] > 0
    assert len(body["results"]) > 0


def test_get_labels_taxonomy_includes_global_stocktake_category() -> None:
    """GST1 must nest under the Global Stocktake category so the frontend filter tree renders it correctly."""
    client = TestClient(app)

    response = client.get("/search/labels-taxonomy")

    body = response.json()
    results_by_id = {result["id"]: result for result in body["results"]}

    assert "category::Global Stocktake" in results_by_id

    gst1 = results_by_id["process::GST1"]
    assert gst1["type"] == "process"
    assert gst1["value"] == "GST1 Submission"
    assert gst1["labels"][0]["type"] == "subconcept_of"
    assert gst1["labels"][0]["value"]["id"] == "category::Global Stocktake"


def test_get_labels_taxonomy_includes_global_stocktake_party_branch() -> None:
    """
    Party must nest under Global Stocktake.

    The existing UNFCCC document types must also nest under Party (in addition
    to their existing UNFCCC parent) so they render under both branches.
    """
    client = TestClient(app)

    response = client.get("/search/labels-taxonomy")

    body = response.json()
    results_by_id = {result["id"]: result for result in body["results"]}

    party = results_by_id["author_type::Party"]
    assert party["type"] == "author_type"
    assert party["value"] == "Party"
    assert party["labels"][0]["type"] == "subconcept_of"
    assert party["labels"][0]["value"]["id"] == "category::Global Stocktake"

    document_type_ids = [
        "entity_type::Nationally Determined Contribution (NDC)",
        "entity_type::National Adaptation Plan (NAP)",
        "entity_type::Biennial Transparency Report (BTR)",
        "entity_type::Long-term Low-emission Development Strategy (LT-LEDS)",
        "entity_type::Biennial Update Report (BUR)",
        "entity_type::Biennial Report (BR)",
        "entity_type::National Communication (NC)",
        "entity_type::National Inventory Report (NIR)",
        "entity_type::Adaptation Communication (AC)",
    ]
    for document_type_id in document_type_ids:
        document_type = results_by_id[document_type_id]
        parent_ids = {relationship["value"]["id"] for relationship in document_type["labels"]}
        assert parent_ids == {"un_convention::UNFCCC", "author_type::Party"}


def test_root_advertises_the_docs_as_schema_org_json_ld() -> None:
    """The root response is how an agent with no prior knowledge finds the docs."""
    client = TestClient(app)

    body = client.get("/").json()

    assert body["@context"] == "https://schema.org"
    assert body["@type"] == "WebAPI"
    documentation = {doc["name"]: doc["url"] for doc in body["documentation"]}
    assert documentation["llms.txt"].endswith("/search/llms.txt")
    assert documentation["OpenAPI schema"].endswith("/search/openapi.json")


def test_root_keeps_the_keys_the_health_check_reads() -> None:
    """
    `/` doubles as the App Runner health check, so `name` and `version` stay.

    Adding JSON-LD around them is additive; dropping them would fail the
    deployment somewhere no test in this file would notice.
    """
    client = TestClient(app)

    body = client.get("/").json()

    assert body["name"] == API_TITLE
    assert body["version"] == API_VERSION


def test_get_llms_txt_serves_the_spec_as_plain_text() -> None:
    client = TestClient(app)

    response = client.get("/search/llms.txt")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.startswith("# Climate Policy Radar")
