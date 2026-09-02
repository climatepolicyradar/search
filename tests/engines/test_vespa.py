"""Tests for Vespa search engine classes and parsing logic."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from hypothesis import given
from vespa.io import VespaQueryResponse

from search.engines import Pagination
from search.engines.dev_vespa import FieldFilter, Filter
from search.engines.vespa import (
    ExactVespaPassageSearchEngine,
    HybridVespaPassageSearchEngine,
    VespaLabelSearchEngine,
    VespaQueryError,
    _build_passage_filter_yql,
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
    request = engine._build_request(
        terms, Pagination(page_size=limit, page_token=offset + 1), None
    )

    assert isinstance(request, dict)
    assert "yql" in request
    assert "ranking.softtimeout.factor" in request
    assert "ranking.profile" in request
    assert "summary" in request

    assert request["ranking.profile"] == "exact_not_stemmed"

    if terms:
        assert request["query_string"] == terms
        assert "text_block_not_stemmed" in request["yql"]
    else:
        # An empty query must not reach a term operator: Vespa rejects it with
        # "The word of a word item cannot be empty".
        assert "query_string" not in request
        assert request["yql"].endswith("where true")


@given(
    terms=search_terms_strategy,
    limit=search_limit_strategy.filter(lambda x: x is not None),
    offset=search_offset_strategy,
)
def test_hybrid_request(terms, limit, offset):
    """Test hybrid request returns the expected fields."""

    engine = HybridVespaPassageSearchEngine()
    request = engine._build_request(
        terms, Pagination(page_size=limit, page_token=offset + 1), None
    )

    assert isinstance(request, dict)
    assert "yql" in request
    assert request["ranking.profile"] == "hybrid"

    if terms:
        assert request["query_string"] == terms
        assert "userInput(@query_string)" in request["yql"]
        assert "nearestNeighbor" in request["yql"]
    else:
        # Nothing to embed, so both the text and nearest-neighbour clauses go.
        assert "query_string" not in request
        assert "input.query(query_embedding)" not in request
        assert request["yql"].endswith("where true")


DOCUMENT_ID = "CCLW.document.i00007398.n0000"


def _topic(wikibase_id: str) -> FieldFilter:
    """A topic condition as `search.testcase` builds it."""
    return FieldFilter(
        field="labels.value.id", op="contains", value=f"concept::{wikibase_id}"
    )


@pytest.mark.parametrize(
    ("filter_group", "expected"),
    [
        # A `concept::` label id becomes a bare wikibase id on `concepts.id`.
        (
            Filter(op="and", filters=[_topic("Q1829")]),
            'concepts.id contains "Q1829"',
        ),
        # ANDed topics need no `sameElement`: each may match a different element
        # of the `concepts` array, which is what "carries both concepts" means.
        (
            Filter(op="and", filters=[_topic("Q567"), _topic("Q1651")]),
            '(concepts.id contains "Q567" and concepts.id contains "Q1651")',
        ),
        (
            Filter(op="or", filters=[_topic("Q567"), _topic("Q1651")]),
            '(concepts.id contains "Q567" or concepts.id contains "Q1651")',
        ),
        # `document_id` is `document_import_id` on this schema.
        (
            Filter(
                op="and",
                filters=[
                    FieldFilter(field="document_id", op="contains", value=DOCUMENT_ID)
                ],
            ),
            f'document_import_id contains "{DOCUMENT_ID}"',
        ),
        (
            Filter(
                op="and",
                filters=[
                    FieldFilter(
                        field="document_id", op="not_contains", value=DOCUMENT_ID
                    )
                ],
            ),
            f'!(document_import_id contains "{DOCUMENT_ID}")',
        ),
        # Nested groups, as `TestCase.filters_json_string` produces for topics.
        (
            Filter(
                op="and",
                filters=[
                    Filter(op="or", filters=[_topic("Q567")]),
                    FieldFilter(field="document_id", op="contains", value=DOCUMENT_ID),
                ],
            ),
            f'(concepts.id contains "Q567" and document_import_id contains "{DOCUMENT_ID}")',
        ),
    ],
)
def test_passage_filter_yql(filter_group: Filter, expected: str) -> None:
    """Filters are translated into `document_passage` YQL."""
    assert _build_passage_filter_yql(filter_group) == expected


@pytest.mark.parametrize(
    "filter_group",
    [
        # Corpus filters share the topic field but use an `agent::` prefix, and
        # `document_passage` has no provider field to map them onto.
        Filter(
            op="or",
            filters=[
                FieldFilter(
                    field="labels.value.id",
                    op="contains",
                    value="agent::Green Climate Fund",
                )
            ],
        ),
        # `principal_id` has no equivalent on `document_passage` either.
        Filter(
            op="and",
            filters=[
                FieldFilter(field="principal_id", op="contains", value="principal-1")
            ],
        ),
    ],
)
def test_unsupported_passage_filter_raises(filter_group: Filter) -> None:
    """
    Unmappable filters raise rather than being dropped.

    A dropped filter would search the whole corpus and return results that still
    look valid.
    """
    with pytest.raises(VespaQueryError):
        _build_passage_filter_yql(filter_group)


def test_exact_request_combines_filters_and_terms() -> None:
    """Filters are applied alongside the search term."""
    engine = ExactVespaPassageSearchEngine()
    filters = Filter(
        op="and",
        filters=[
            _topic("Q1829"),
            FieldFilter(field="document_id", op="contains", value=DOCUMENT_ID),
        ],
    ).model_dump_json()

    request = engine._build_request(
        "flooding", Pagination(page_size=5, page_token=1), filters
    )

    assert request["yql"] == (
        "select * from sources document_passage where "
        "(text_block_not_stemmed contains ({stem: false}@query_string)) and "
        f'(concepts.id contains "Q1829" and document_import_id contains "{DOCUMENT_ID}")'
    )
    assert request["query_string"] == "flooding"


def test_exact_request_filters_only() -> None:
    """A topic-only test case searches on its filters alone."""
    engine = ExactVespaPassageSearchEngine()
    filters = Filter(op="and", filters=[_topic("Q1829")]).model_dump_json()

    request = engine._build_request("", Pagination(page_size=5, page_token=1), filters)

    assert request["yql"] == (
        'select * from sources document_passage where concepts.id contains "Q1829"'
    )
    assert "query_string" not in request


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
    result = exact_vespa_passage_engine._parse_vespa_response(response)

    assert len(result.results) == 3
    assert result.results[0].text == "This is a sample passage about climate change."
    assert result.results[1].text == "Second passage"
    assert result.results[2].text == "Third passage"


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
        "type": "topic",
        "value": "multilateral climate fund",
    }


@given(
    terms=search_terms_strategy,
    limit=search_limit_strategy.filter(lambda x: x is not None),
    offset=search_offset_strategy,
)
def test_label_request_parameters(terms, limit, offset):
    """Test label request contains correct parameters with property-based testing."""
    engine = VespaLabelSearchEngine()
    pagination = Pagination(page_size=limit, page_token=offset + 1)
    request = engine._build_request(terms, pagination, None)

    assert isinstance(request, dict)
    assert "yql" in request
    assert "query_string" in request
    assert request["query_string"] == terms
    assert request["hits"] == limit
    assert request["offset"] == offset * limit


def test_parse_vespa_label_response(
    vespa_label_engine, mock_vespa_label_response, sample_label_fields
):
    """Test parsing a Vespa response with multiple labels."""
    fields_1 = sample_label_fields.copy()
    fields_2 = {
        "id": "abc123",
        "type": "topic",
        "value": "air pollution",
    }
    fields_3 = {
        "id": "xyz789",
        "type": "topic",
        "value": "renewable energy",
    }

    response = mock_vespa_label_response([fields_1, fields_2, fields_3])
    result = vespa_label_engine._parse_vespa_response(response)

    assert len(result.results) == 3
    assert result.results[0].value == "multilateral climate fund"
    assert result.results[1].value == "air pollution"
    assert result.results[2].value == "renewable energy"
