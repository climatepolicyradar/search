"""Tests for Vespa search engine classes and parsing logic."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given
from vespa.io import VespaQueryResponse

from search.engines.vespa import (
    ExactVespaPassageSearchEngine,
    HybridVespaPassageSearchEngine,
    VespaLabelSearchEngine,
)
from tests.common_strategies import (
    search_limit_strategy,
    search_offset_strategy,
    search_terms_strategy,
)


@pytest.fixture
def exact_vespa_passage_engine():
    """
    Create an ExactVespaPassageSearchEngine instance for testing.

    :return: ExactVespaPassageSearchEngine instance
    """
    return ExactVespaPassageSearchEngine()


@pytest.fixture
def hybrid_vespa_passage_engine():
    """
    Create a HybridVespaPassageSearchEngine instance for testing.

    :return: HybridVespaPassageSearchEngine instance
    """
    return HybridVespaPassageSearchEngine()


@pytest.fixture
def mock_vespa_passage_response():
    """
    Factory fixture for creating mock VespaQueryResponse objects for passage search.

    Returns:
        callable: Function that takes a list of passage field dicts and returns a mock VespaQueryResponse
    """

    def _create_response(
        passage_fields_list: list[dict[str, Any]],
    ) -> VespaQueryResponse:
        """
        Create a mock VespaQueryResponse with the given passage fields.

        Args:
            passage_fields_list (list[dict[str, Any]]): List of field dicts for each passage

        Returns:
            VespaQueryResponse: Mock response object
        """
        children = [{"fields": fields} for fields in passage_fields_list]
        response_json = {"root": {"children": children}}

        mock_response = MagicMock(spec=VespaQueryResponse)
        mock_response.json = response_json
        return mock_response

    return _create_response


@pytest.fixture
def sample_passage_fields():
    """
    A standard set of passage fields for testing.

    Returns:
        dict: Dictionary with all expected Vespa passage fields
    """

    return {
        "text_block": "This is a sample passage about climate change.",
        "text_block_id": "12345",
        "family_name": "Climate Action Plan",
        "family_description": "A comprehensive plan for climate action",
        "document_source_url": "https://example.com/document",
        "document_import_id": "UNFCCC.document.i00001234.n0000",
    }


@given(
    terms=search_terms_strategy,
    limit=search_limit_strategy.filter(lambda x: x is not None),
    offset=search_offset_strategy,
)
def test_exact_request(terms, limit, offset):
    """Test exact request returns the expected fields."""

    engine = ExactVespaPassageSearchEngine()
    request = engine._build_request(terms, limit, offset)

    assert isinstance(request, dict)
    assert "yql" in request
    assert "query_string" in request
    assert "ranking.softtimeout.factor" in request
    assert "ranking.profile" in request
    assert "summary" in request

    assert request["query_string"] == terms
    assert request["ranking.profile"] == "exact_not_stemmed"


@given(
    terms=search_terms_strategy,
    limit=search_limit_strategy.filter(lambda x: x is not None),
    offset=search_offset_strategy,
)
def test_hybrid_request(terms, limit, offset):
    """Test hybrid request returns the expected fields."""

    engine = HybridVespaPassageSearchEngine()
    request = engine._build_request(terms, limit, offset)

    assert isinstance(request, dict)
    assert "yql" in request
    assert "query_string" in request
    assert request["query_string"] == terms
    assert request["ranking.profile"] == "hybrid"
    assert "userInput(@query_string)" in request["yql"]
    assert "nearestNeighbor" in request["yql"]


def test_parse_vespa_passage_response(
    exact_vespa_passage_engine, mock_vespa_passage_response, sample_passage_fields
):
    """Test parsing a Vespa response with multiple passages."""

    fields_1 = sample_passage_fields.copy()
    fields_2 = {
        **sample_passage_fields,
        "text_block_id": "67890",
        "text_block": "Second passage",
    }
    fields_3 = {
        **sample_passage_fields,
        "text_block_id": "11111",
        "text_block": "Third passage",
    }

    response = mock_vespa_passage_response([fields_1, fields_2, fields_3])
    passages = exact_vespa_passage_engine._parse_vespa_response(response)

    assert len(passages) == 3
    assert passages[0].text == "This is a sample passage about climate change."
    assert passages[1].text == "Second passage"
    assert passages[2].text == "Third passage"


@pytest.fixture
def vespa_label_engine():
    """
    Create a VespaLabelSearchEngine instance for testing.

    :return: VespaLabelSearchEngine instance
    """
    return VespaLabelSearchEngine()


@pytest.fixture
def mock_vespa_label_response():
    """
    Factory fixture for creating mock VespaQueryResponse objects for label search.

    Returns:
        callable: Function that takes a list of label field dicts and returns a mock VespaQueryResponse
    """

    def _create_response(label_fields_list: list[dict[str, Any]]) -> VespaQueryResponse:
        """
        Create a mock VespaQueryResponse with the given label fields.

        Args:
            label_fields_list (list[dict[str, Any]]): List of field dicts for each label

        Returns:
            VespaQueryResponse: Mock response object
        """
        children = [{"fields": fields} for fields in label_fields_list]
        response_json = {"root": {"children": children}}
        mock_response = MagicMock(spec=VespaQueryResponse)
        mock_response.json = response_json
        return mock_response

    return _create_response


@pytest.fixture
def sample_label_fields():
    """
    A standard set of label fields for testing.

    Returns:
        dict: Dictionary with all expected Vespa label/concept fields
    """
    return {
        "id": "zv3r45ae",
        "wikibase_id": "Q1363",
        "preferred_label": "multilateral climate fund",
        "description": "Climate finance fund",
        "alternative_labels": ["climate fund", "MCF"],
        "negative_labels": [],
    }


@given(
    terms=search_terms_strategy,
    limit=search_limit_strategy.filter(lambda x: x is not None),
    offset=search_offset_strategy,
)
def test_label_request_parameters(terms, limit, offset):
    """Test label request contains correct parameters with property-based testing."""
    engine = VespaLabelSearchEngine()
    request = engine._build_request(terms, limit, offset)

    assert isinstance(request, dict)
    assert "yql" in request
    assert "query_string" in request
    assert request["query_string"] == terms
    assert f"limit {limit}" in request["yql"]
    assert f"offset {offset}" in request["yql"]


def test_parse_vespa_label_response(
    vespa_label_engine, mock_vespa_label_response, sample_label_fields
):
    """Test parsing a Vespa response with multiple labels."""
    fields_1 = sample_label_fields.copy()
    fields_2 = {
        **sample_label_fields,
        "id": "abc123",
        "preferred_label": "air pollution",
        "alternative_labels": ["atmospheric pollution"],
        "description": "",
    }
    fields_3 = {
        **sample_label_fields,
        "id": "xyz789",
        "preferred_label": "renewable energy",
        "alternative_labels": ["clean energy"],
        "description": "Sustainable power sources",
    }

    response = mock_vespa_label_response([fields_1, fields_2, fields_3])
    labels = vespa_label_engine._parse_vespa_response(response)

    assert len(labels) == 3
    assert labels[0].preferred_label == "multilateral climate fund"
    assert labels[1].preferred_label == "air pollution"
    assert labels[2].preferred_label == "renewable energy"
