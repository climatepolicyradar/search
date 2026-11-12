from http import HTTPStatus

from fastapi.testclient import TestClient

from api.state import State
from search.data_in_models import Label, LabelRelationship
from search.engines import VespaError
from search.label import LabelSearchResult
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)
from tests.engines.dev_vespa.stub_labels_search_engine import StubLabelSearchEngine

CONCEPT = Label(
    id="concept::Q1",
    type="concept",
    value="Flooding",
    labels=[],
)

KEYWORD = Label(
    id="keyword::Flood",
    type="keyword",
    value="Flood",
    labels=[LabelRelationship(type="subconcept_of", value=CONCEPT)],

)
VESPA_DOWN = VespaError("Vespa is down", status_code=None)


def _fetched(label: Label) -> LabelSearchResult:
    return LabelSearchResult.model_validate({**label.model_dump(), "alternative_labels": []})


async def _load(state: State, labels: StubLabelSearchEngine) -> None:
    labels.add_all_labels_response([_fetched(CONCEPT), _fetched(KEYWORD)])
    await state.taxonomy._refresh()


def _nodes(response: dict) -> dict[str, dict]:
    return {node["id"]: node for node in response["data"]}


async def test_a_count_lands_on_its_node(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({"concept::Q1": 7})
    response = test_client.get("/search/labels:taxonomy")
    assert _nodes(response.json())["concept::Q1"]["count"] == 7


async def test_a_label_vespa_counted_nothing_for_is_zero(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    response = test_client.get("/search/labels:taxonomy")
    assert _nodes(response.json())["concept::Q1"]["count"] == 0


async def test_a_pattern_returns_the_minimal_connecting_tree(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({"keyword::Flood": 3})
    response = test_client.get("/search/labels:taxonomy", params={"include": "**/keyword::*"})
    nodes = response.json()["data"]
    assert [node["id"] for node in nodes] == ["concept::Q1"]
    assert [child["id"] for child in nodes[0]["children"]] == ["keyword::Flood"]


async def test_the_ancestors_kept_are_counted_too(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    test_client.get("/search/labels:taxonomy", params={"include": "**/keyword::*"})
    assert documents.label_counts_requests[0].label_types == ["concept", "keyword"]


async def test_a_pattern_returns_the_tree_leading_to_the_match(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    response = test_client.get("/search/labels:taxonomy", params={"include": "**/keyword::Flood"})
    nodes = response.json()["data"]
    assert [node["id"] for node in nodes] == ["concept::Q1"]
    assert [child["id"] for child in nodes[0]["children"]] == ["keyword::Flood"]


async def test_a_match_under_another_match_stays_nested(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    response = test_client.get(
        "/search/labels:taxonomy",
        params={"include": ["**/concept::*", "**/keyword::Flood"]},
    )
    nodes = response.json()["data"]
    assert [node["id"] for node in nodes] == ["concept::Q1"]
    assert [child["id"] for child in nodes[0]["children"]] == ["keyword::Flood"]


async def test_a_query_narrows_the_documents_counted(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    test_client.get("/search/labels:taxonomy", params={"query": "flood"})
    assert documents.label_counts_requests[0].query == "flood"


async def test_without_a_query_every_document_is_counted(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    test_client.get("/search/labels:taxonomy")
    assert documents.label_counts_requests[0].query is None


async def test_children_are_nested_under_their_parent(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response({})
    response = test_client.get("/search/labels:taxonomy")
    children = _nodes(response.json())["concept::Q1"]["children"]
    assert [child["id"] for child in children] == ["keyword::Flood"]


def test_an_unloaded_taxonomy_is_unavailable(test_client: TestClient) -> None:
    response = test_client.get("/search/labels:taxonomy")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


async def test_a_failed_count_is_unavailable(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
    documents: StubDocumentSearchEngine,
) -> None:
    await _load(state, labels)
    documents.add_label_counts_response(VESPA_DOWN)
    response = test_client.get("/search/labels:taxonomy")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


async def test_malformed_filters_are_rejected(
    test_client: TestClient,
    state: State,
    labels: StubLabelSearchEngine,
) -> None:
    await _load(state, labels)
    response = test_client.get("/search/labels:taxonomy", params={"filters": "{not json"})
    assert response.status_code == HTTPStatus.BAD_REQUEST
