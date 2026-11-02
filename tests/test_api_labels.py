"""
Regression tests for ``GET /search/labels``.

The label search engine returns :class:`~search.data_in_models.Label`
(``DataInLabel``). The route response model must use the same type; using
``search.label.Label`` validates empty result sets but returns 500 once any hit
parses successfully.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from search.engines import ListResponse
from search.label import LabelSearchResult


@pytest.fixture
def labels_client():
    """
    Provide a test client with Vespa label search mocked.

    :yield: HTTP client for the search API.
    :rtype: TestClient
    """
    data_in_label = LabelSearchResult(
        id="concept::Q684",
        type="concept",
        value="indigenous people",
        alternative_labels=["first nations", "aboriginal peoples"],
    )
    with patch("api.routers.DevVespaLabelSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.asearch = AsyncMock()
        mock_engine.asearch.return_value = ListResponse(
            results=[data_in_label],
            total_size=1,
            next_page_token=None,
        )
        yield TestClient(app)


def test_labels_endpoint_serialises_data_in_label_results(
    labels_client: TestClient,
) -> None:
    """
    Ensure ``/search/labels`` returns 200 when the engine yields ``DataInLabel``.

    Regression for mismatched ``SearchResponse[Label]`` vs engine output
    after #304: Pydantic rejected valid hits and the API responded with 500.

    :param labels_client: Client with mocked label search engine.
    :type labels_client: TestClient
    :return: ``None``.
    :rtype: None
    """
    response = labels_client.get("/search/labels", params={"page_size": 10})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["results"]) == 1
    assert payload["results"][0] == {
        "id": "concept::Q684",
        "type": "concept",
        "value": "indigenous people",
        "alternative_labels": ["first nations", "aboriginal peoples"],
        "labels": [],
    }


def test_labels_endpoint_exposes_alternative_labels(
    labels_client: TestClient,
) -> None:
    """
    Ensure ``/search/labels`` returns a concept's other names (FUS-570).

    The filter lookup matches the quick-search box against this field, so that
    typing "first nations" surfaces the "indigenous people" topic. Vespa has
    always indexed and ranked ``alternative_labels``; before FUS-570 the engine
    read them only into ``debug_info`` and dropped them from the response.

    :param labels_client: Client with mocked label search engine.
    :type labels_client: TestClient
    :return: ``None``.
    :rtype: None
    """
    response = labels_client.get("/search/labels", params={"page_size": 10})

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["alternative_labels"] == [
        "first nations",
        "aboriginal peoples",
    ]


def test_labels_taxonomy_does_not_expose_alternative_labels() -> None:
    """
    Ensure ``/search/labels-taxonomy`` keeps the shared ``DataInLabel`` shape.

    The alias field belongs to the label *search* response only. Letting it
    reach the shared model would put a mostly-empty array on every nested label
    of every document and passage response -- the cost Option C exists to
    avoid.

    :return: ``None``.
    :rtype: None
    """
    response = TestClient(app).get("/search/labels-taxonomy")

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results, "taxonomy should not be empty"
    assert all("alternative_labels" not in result for result in results)
