"""Unit tests for TestCase implementations."""

import pytest

from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.engines.dev_vespa import (
    Filter,
    _build_filter_yql,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)
from search.label import Label
from search.testcase import RelativeOrderTestCase


class StubLabelSearchEngine(SearchEngine[Label]):
    """A search engine which always returns the labels it was constructed with."""

    model_class = Label

    def __init__(self, result_ids: list[str]):
        self.results = [Label(id=result_id) for result_id in result_ids]

    def search(
        self,
        query: str,  # noqa: ARG002
        pagination: Pagination,
        order_by: list[OrderBy],  # noqa: ARG002
        filters_json_string: str | None,  # noqa: ARG002
    ) -> ListResponse[Label]:
        """Return the stubbed results, truncated to the requested page size."""
        results = self.results[: pagination.page_size]
        return ListResponse(
            results=results, total_size=len(self.results), next_page_token=None
        )

    def count(self, query: str) -> int:  # noqa: ARG002
        """Return the number of stubbed results."""
        return len(self.results)


def _test_case(**kwargs) -> RelativeOrderTestCase[Label]:
    return RelativeOrderTestCase[Label](
        search_terms="climate change",
        description="'a' should rank above 'b'",
        higher_result_id="a",
        lower_result_id="b",
        **kwargs,
    )


@pytest.mark.parametrize(
    ("result_ids", "expected_passed"),
    [
        (["a", "b"], True),
        (["b", "a"], False),
        (["x", "a", "y", "b"], True),
        (["x", "b", "y", "a"], False),
        # The lower result missing entirely means it ranks below the cutoff.
        (["x", "a", "y"], True),
        # The higher result must be present for the ordering to hold.
        (["x", "b", "y"], False),
        ([], False),
    ],
)
def test_relative_order_passes_when_higher_result_ranks_above_lower(
    result_ids: list[str], expected_passed: bool
):
    test_case = _test_case()

    passed, results = test_case.run_against(StubLabelSearchEngine(result_ids))

    assert passed == expected_passed
    assert [result.id for result in results] == result_ids


def test_topics_or_matches_any_topic() -> None:
    """With ``topics_or``, the topic clauses are ORed with each other."""
    test_case = _test_case(
        topics=["Q567", "Q1651"],
        topics_or=True,
        document_id="CPR.document.i00004961.n0000",
    )

    filters_json_string = test_case.filters_json_string()

    assert filters_json_string is not None
    assert _build_filter_yql(
        Filter.model_validate_json(filters_json_string),
        passages_filter_field_to_vespa_field_map,
        passages_filter_struct_field_to_vespa_field_map,
    ) == (
        '((labels contains sameElement(id contains "concept::Q567") '
        'or labels contains sameElement(id contains "concept::Q1651")) '
        'and document_id contains "CPR.document.i00004961.n0000")'
    )


def test_already_prefixed_topics_are_left_alone() -> None:
    """A topic given as ``concept::Q567`` isn't prefixed twice."""
    filters_json_string = _test_case(topics=["concept::Q567"]).filters_json_string()

    assert filters_json_string is not None
    assert (
        _build_filter_yql(
            Filter.model_validate_json(filters_json_string),
            passages_filter_field_to_vespa_field_map,
            passages_filter_struct_field_to_vespa_field_map,
        )
        == 'labels contains sameElement(id contains "concept::Q567")'
    )


def test_no_topics_leaves_filters_unset() -> None:
    """A test case without topics or other filters sends no filter JSON."""
    assert _test_case().filters_json_string() is None


def test_relative_order_rejects_identical_result_ids():
    with pytest.raises(
        ValueError, match="higher_result_id and lower_result_id must be different"
    ):
        RelativeOrderTestCase[Label](
            search_terms="climate change",
            description="invalid",
            higher_result_id="a",
            lower_result_id="a",
        )
