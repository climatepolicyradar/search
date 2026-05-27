"""
Regression tests for ``GET /search/labels``.

The label search engine returns :class:`~search.data_in_models.Label`
(``DataInLabel``). The route response model must use the same type; using
``search.label.Label`` validates empty result sets but returns 500 once any hit
parses successfully.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from search.data_in_models import Label as DataInLabel
from search.engines import ListResponse


@pytest.fixture
def labels_client():
    """
    Provide a test client with Vespa label search mocked.

    :yield: HTTP client for the search API.
    :rtype: TestClient
    """
    data_in_label = DataInLabel(
        id="geography::Romania",
        type="geography",
        value="Romania",
    )
    with patch("api.routers.DevVespaLabelSearchEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.search.return_value = ListResponse(
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
        "id": "geography::Romania",
        "type": "geography",
        "value": "Romania",
        "labels": [],
    }
