"""
Tests for the dev Vespa label search engine (DevVespaLabelSearchEngine).

These tests focus on:
- verifying the regex / YQL generated for different query terms
- ensuring labels like "concept::air pollution risk" are parsed correctly
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from search.data_in_models import Label
from search.engines.dev_vespa import DevVespaLabelSearchEngine


@pytest.fixture
def dev_label_engine() -> DevVespaLabelSearchEngine:
    """
    Create a DevVespaLabelSearchEngine instance for testing.

    Returns:
        DevVespaLabelSearchEngine: engine under test
    """
    return DevVespaLabelSearchEngine()


@pytest.fixture
def mock_requests_post(monkeypatch):
    """
    Fixture to monkeypatch requests.post used inside DevVespaLabelSearchEngine.search.

    It returns a MagicMock whose .json() can be controlled per-test.
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
    monkeypatch.patch.object(requests, "post", mock_post)

    return mock_post


def _make_grouping_response(values: list[str]) -> dict[str, Any]:
    """
    Build a minimal Vespa-like grouping response.

    Args:
        values: List of `"{type}::{value}"` strings, e.g. ["concept::air pollution risk"]

    Returns:
        dict: JSON structure similar to Vespa grouping response for labels.
    """
    # Shape: root -> children[0] -> children[*] -> value
    return {
        "root": {
            "children": [{"children": [{"value": v, "children": []} for v in values]}]
        }
    }


@pytest.mark.parametrize(
    "query, expected_fragment",
    [
        # NOTE: keep these in sync with the regex logic in DevVespaLabelSearchEngine.search
        # @related: DevVespaLabelSearchEngine.search
        ("air", r"(?i)^concept::.*air.*"),
        ("air pollution", r"(?i)^concept::.*air pollution.*"),
        ("pollution", r"(?i)^concept::.*pollution.*"),
        ("risk", r"(?i)^concept::.*risk.*"),
    ],
)
def test_dev_label_engine_builds_substring_regex_for_concepts(
    dev_label_engine: DevVespaLabelSearchEngine,
    mock_requests_post: MagicMock,
    query: str,
    expected_fragment: str,
):
    """
    Ensure the dev label engine builds a YQL regex that matches the query
    anywhere in the value part of `type::value` for the given label_type.

    This test assumes label_type="concept" to cover the "air pollution risk" case.
    """
    mock_requests_post.json_return_value = {"root": {}}

    dev_label_engine.search(query=query, label_type="concept")

    sent = mock_requests_post.last_json  # type: ignore[attr-defined]
    yql = sent["yql"]

    # The regex should appear in the YQL string.
    assert expected_fragment in yql


def test_dev_label_engine_parses_air_pollution_risk_label(
    dev_label_engine: DevVespaLabelSearchEngine,
    mock_requests_post: MagicMock,
):
    """
    Given a Vespa grouping response containing "concept::air pollution risk",
    ensure the dev label engine returns a Label with the expected type and value.
    """
    label_values = [
        "concept::air pollution risk",
        "concept::renewable energy",
    ]
    mock_response_json = _make_grouping_response(label_values)
    mock_requests_post.json_return_value = mock_response_json

    labels = dev_label_engine.search(query="pollution", label_type="concept")

    assert all(isinstance(label, Label) for label in labels)

    # Extract the "air pollution risk" label.
    values = {(label.type, label.value) for label in labels}
    assert ("concept", "air pollution risk") in values
    assert ("concept", "renewable energy") in values
