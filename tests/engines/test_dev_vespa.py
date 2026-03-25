"""Tests for the dev Vespa label search engines."""

from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from search.engines import Pagination
from search.engines.dev_vespa import (
    DevVespaLabelTypeaheadSearchEngine,
)
from search.label import Label


@pytest.fixture
def mock_requests_post(monkeypatch):
    """
    Monkeypatch requests.post.

    :return: A MagicMock whose .json() can be controlled per-test.
    """
    mock_post = MagicMock()

    def _fake_post(
        url: str, json: dict[str, Any], timeout: int, headers: dict[str, str]
    ):
        # Store the last call's JSON body so tests can inspect the built YQL / regex.
        mock_post.last_json = json  # type: ignore[attr-defined]
        response = MagicMock()

        # Each test can overwrite `response.json.return_value` as needed.
        response.json.return_value = getattr(
            mock_post, "json_return_value", {"root": {}}
        )
        return response

    mock_post.side_effect = _fake_post
    monkeypatch.setattr(requests, "post", mock_post)

    return mock_post


# region DevVespaLabelTypeaheadSearchEngine tests


@pytest.fixture
def dev_typeahead_engine() -> DevVespaLabelTypeaheadSearchEngine:
    return DevVespaLabelTypeaheadSearchEngine()


def _make_grouping_response(values: list[str]) -> dict[str, Any]:
    """
    Build a minimal Vespa-like grouping response.

    Expected shape for DevVespaLabelSearchEngine:
    root -> children[0] -> children (groups) -> children (values) -> value

    :param list[str] values: List of `"{type}::{value}"` strings, e.g.
        ["concept::air pollution risk"]

    :return dict: JSON structure similar to Vespa grouping response for
        labels.
    """
    return {
        "root": {
            "children": [{"children": [{"children": [{"value": v} for v in values]}]}]
        }
    }


@pytest.mark.parametrize(
    "query, expected_fragment",
    [
        # NOTE: keep these in sync with the regex logic in DevVespaLabelSearchEngine.search
        # @related: DevVespaLabelSearchEngine.search
        ("air", r"(?i)^concept::.*air.*"),
        ("air pollution", r"(?i)^concept::.*air\ pollution.*"),
        ("pollution", r"(?i)^concept::.*pollution.*"),
        ("risk", r"(?i)^concept::.*risk.*"),
    ],
)
def test_typeahead_engine_builds_substring_regex_for_concepts(
    dev_typeahead_engine: DevVespaLabelTypeaheadSearchEngine,
    mock_requests_post: MagicMock,
    query: str,
    expected_fragment: str,
):
    """
    Verify dev engine allows partial matching on label values.

    Ensure the dev label engine builds a YQL regex that matches the
    query anywhere in the value part of `type::value` for the given
    label_type.

    This test assumes label_type="concept" to cover the "air pollution
    risk" case.
    """
    mock_requests_post.json_return_value = {"root": {}}

    dev_typeahead_engine.search(
        query=query,
        label_type="concept",
        pagination=Pagination(page_token=1, page_size=10),
    )

    sent = mock_requests_post.last_json  # type: ignore[attr-defined]
    yql = sent["yql"]

    # The regex should appear in the YQL string.
    assert expected_fragment in yql


def test_typeahead_engine_returns_correct_type_and_value(
    dev_typeahead_engine: DevVespaLabelTypeaheadSearchEngine,
    mock_requests_post: MagicMock,
):
    """
    Check dev engine returns correct type.

    GIVEN a Vespa grouping response
    WHEN that response contains "concept::air pollution risk"
    THEN ensure the dev label engine returns a Label with the expected
        type and value.
    """
    label_values = ["concept::air pollution risk"]
    mock_requests_post.json_return_value = _make_grouping_response(label_values)

    labels = dev_typeahead_engine.search(
        query="pollution",
        label_type="concept",
        pagination=Pagination(page_token=1, page_size=10),
    )

    assert all(isinstance(label, Label) for label in labels)

    # Extract the "air pollution risk" label.
    values = {(label.type, label.value) for label in labels}
    assert ("concept", "air pollution risk") in values


# endregion
