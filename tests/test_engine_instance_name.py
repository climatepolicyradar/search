"""Tests that the Vespa instance name is surfaced in the engine id."""

import pytest

from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
)
from search.identifiers import generate_id


def _dev_engine(instance_name):
    return DevVespaPassageSearchEngine(
        settings=Settings(
            vespa_endpoint="http://localhost:8080",  # type: ignore[arg-type]
            vespa_read_token="token",  # nosec B106
            vespa_dev_instance_name=instance_name,
        )
    )


@pytest.mark.parametrize("instance_name", ["dev-instance", "alice", "sample-42"])
def test_engine_id_and_repr_factor_in_instance_name(instance_name):
    """Any instance name is surfaced on the engine and changes id"""
    dev = _dev_engine(instance_name)
    full = _dev_engine(None)

    assert dev.instance_name == instance_name
    assert instance_name in repr(dev)
    assert dev.id != full.id  # differs from the no-instance id
    assert dev.id != _dev_engine("other").id  # differs per instance name


def test_engine_with_no_instance_matches_pre_feature_behaviour():
    """A None instance leaves the repr unchanged; the id also folds in parameters"""
    full = _dev_engine(None)
    assert full.instance_name is None
    assert full.id == generate_id(
        "DevVespaPassageSearchEngine (Passage)",
        ("exact_weight", 0.1),
        ("ranking_profile", "bm25_multiplicative"),
        ("topic_weight", 1.0),
    )
    assert repr(full) == "DevVespaPassageSearchEngine (Passage)"


def test_engine_id_factors_in_parameters():
    """Engines differing only by a tuning parameter get distinct ids, same name"""
    settings = Settings(
        vespa_endpoint="http://localhost:8080",  # type: ignore[arg-type]
        vespa_read_token="token",  # nosec B106
    )
    default = DevVespaPassageSearchEngine(settings=settings)
    bm25 = DevVespaPassageSearchEngine(settings=settings, ranking_profile="bm25")

    assert default.name == bm25.name == "DevVespaPassageSearchEngine"
    assert bm25.parameters == {
        "ranking_profile": "bm25",
        "topic_weight": 1.0,
        "exact_weight": 0.1,
    }
    assert default.id != bm25.id


def test_passage_engine_id_factors_in_topic_weight():
    """Two topic weights on the same rank profile are distinguishable runs"""
    settings = Settings(
        vespa_endpoint="http://localhost:8080",  # type: ignore[arg-type]
        vespa_read_token="token",  # nosec B106
    )
    on = DevVespaPassageSearchEngine(settings=settings)
    off = DevVespaPassageSearchEngine(settings=settings, topic_weight=0.0)

    assert on.name == off.name == "DevVespaPassageSearchEngine"
    assert on.id != off.id


def test_document_engine_id_factors_in_topic_weight():
    """Same for the document engine's topic weight"""
    settings = Settings(
        vespa_endpoint="http://localhost:8080",  # type: ignore[arg-type]
        vespa_read_token="token",  # nosec B106
    )
    on = DevVespaDocumentSearchEngine(settings=settings)
    off = DevVespaDocumentSearchEngine(settings=settings, topic_weight=0.0)

    assert on.name == off.name == "DevVespaDocumentSearchEngine"
    assert on.id != off.id
