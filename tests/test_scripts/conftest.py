"""Pytest configuration and shared fixtures for data uploader script tests."""

import sys
from unittest.mock import MagicMock

import pytest
from datasets import Dataset

from search.config import get_git_root

# Add project root to sys.path so scripts can be imported
project_root = get_git_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture
def create_mock_huggingface_dataset():
    """
    Factory for HuggingFace datasets that support filtering.

    The mock supports:
    - len(dataset) - returns row count
    - iteration - yields rows
    - dataset.filter() - applies filter function and returns filtered mock
    """

    def _create_mock_dataset(rows: list[dict]):
        mock = MagicMock(spec=Dataset)
        mock.__len__.return_value = len(rows)
        mock.__iter__.return_value = iter(rows)

        def filter_func(func, desc=None):
            filtered = [row for row in rows if func(row)]
            return _create_mock_dataset(filtered)

        mock.filter.side_effect = filter_func
        return mock

    return _create_mock_dataset


@pytest.fixture
def mock_wikibase_concepts():
    """
    Generate mock Wikibase concept objects

    Different objects have different sets of fields populated.
    """
    concepts = []

    # Concept 1: Full concept with all fields
    concept1 = MagicMock()
    concept1.preferred_label = "Climate Change Mitigation"
    concept1.alternative_labels = ["Climate mitigation", "Emissions reduction"]
    concept1.negative_labels = ["Not adaptation"]
    concept1.description = "Actions to reduce greenhouse gas emissions"
    concept1.wikibase_id = "Q1001"
    concepts.append(concept1)

    # Concept 2: Concept with None description
    concept2 = MagicMock()
    concept2.preferred_label = "Renewable Energy"
    concept2.alternative_labels = ["Green energy", "Clean energy"]
    concept2.negative_labels = []
    concept2.description = None
    concept2.wikibase_id = "Q1002"
    concepts.append(concept2)

    # Concept 3: Concept with empty alternative labels
    concept3 = MagicMock()
    concept3.preferred_label = "Carbon Tax"
    concept3.alternative_labels = []
    concept3.negative_labels = ["Carbon trading"]
    concept3.description = "Tax on carbon emissions"
    concept3.wikibase_id = "Q1003"
    concepts.append(concept3)

    # Concept 4: Minimal concept
    concept4 = MagicMock()
    concept4.preferred_label = "Deforestation"
    concept4.alternative_labels = []
    concept4.negative_labels = []
    concept4.description = None
    concept4.wikibase_id = "Q1004"
    concepts.append(concept4)

    return concepts


@pytest.fixture
def ssm_with_wikibase_params(ssm_client):
    """Pre-populate mocked SSM with Wikibase credentials."""
    ssm_client.put_parameter(
        Name="/Wikibase/Cloud/ServiceAccount/Username",
        Value="test-user",
        Type="String",
    )
    ssm_client.put_parameter(
        Name="/Wikibase/Cloud/ServiceAccount/Password",
        Value="test-pass",
        Type="SecureString",
    )
    ssm_client.put_parameter(
        Name="/Wikibase/Cloud/URL", Value="https://test.example.com", Type="String"
    )
    return ssm_client
