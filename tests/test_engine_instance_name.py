"""Tests that the Vespa instance name is surfaced in the engine id and W&B config."""

from unittest.mock import MagicMock

import pytest

from search import weights_and_biases
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
)
from search.identifiers import generate_id
from search.label import Label
from search.passage import Passage


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
        "DevVespaPassageSearchEngine (Passage)", ("ranking_profile", "nativerank")
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
    assert bm25.parameters == {"ranking_profile": "bm25"}
    assert default.id != bm25.id


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


@pytest.mark.parametrize("instance_name", ["dev-instance", "alice"])
def test_log_test_results_logs_instance_in_wandb_config(
    monkeypatch, simple_test_result, instance_name
):
    """Instance name the engine carries lands in the W&B config"""
    monkeypatch.setattr(
        weights_and_biases.config, "DISABLE_WANDB", True
    )  # skip SSM auth in __init__
    monkeypatch.setattr(weights_and_biases.wandb, "Table", MagicMock())

    captured = {}

    def fake_new_run(self, project, config=None, **kwargs):
        captured["config"] = config
        return MagicMock()

    monkeypatch.setattr(weights_and_biases.WandbSession, "new_run", fake_new_run)

    engine = _dev_engine(instance_name)
    weights_and_biases.WandbSession().log_test_results(
        test_results=[simple_test_result],
        primitive=Passage,
        search_engine=engine,
    )

    assert captured["config"]["search_engine_dev_instance_name"] == instance_name
    assert captured["config"]["search_engine_id"] == engine.id


def test_log_test_results_logs_engine_parameters_in_wandb_config(
    monkeypatch, simple_test_result
):
    """Engine tuning parameters land in the W&B config, not in the engine name."""
    monkeypatch.setattr(
        weights_and_biases.config, "DISABLE_WANDB", True
    )  # skip SSM auth in __init__
    monkeypatch.setattr(weights_and_biases.wandb, "Table", MagicMock())

    captured = {}

    def fake_new_run(self, project, config=None, **kwargs):
        captured["config"] = config
        return MagicMock()

    monkeypatch.setattr(weights_and_biases.WandbSession, "new_run", fake_new_run)

    engine = DevVespaDocumentSearchEngine(
        settings=Settings(
            vespa_endpoint="http://localhost:8080",  # type: ignore[arg-type]
            vespa_read_token="token",  # nosec B106
        ),
        topic_weight=0.0,
    )
    weights_and_biases.WandbSession().log_test_results(
        test_results=[simple_test_result],
        primitive=Passage,
        search_engine=engine,
    )

    assert captured["config"]["search_engine.topic_weight"] == 0.0
    assert captured["config"]["search_engine_name"] == "DevVespaDocumentSearchEngine"


def test_engines_without_parameters_are_unchanged(monkeypatch, simple_test_result):
    """An engine with no tuning parameters keeps its old id and W&B config."""
    monkeypatch.setattr(weights_and_biases.config, "DISABLE_WANDB", True)
    monkeypatch.setattr(weights_and_biases.wandb, "Table", MagicMock())

    captured = {}

    def fake_new_run(self, project, config=None, **kwargs):
        captured["config"] = config
        return MagicMock()

    monkeypatch.setattr(weights_and_biases.WandbSession, "new_run", fake_new_run)

    engine = DevVespaLabelSearchEngine(
        settings=Settings(
            vespa_endpoint="http://localhost:8080",  # type: ignore[arg-type]
            vespa_read_token="token",  # nosec B106
        )
    )
    assert engine.parameters == {}
    assert engine.id == generate_id(str(engine))

    weights_and_biases.WandbSession().log_test_results(
        test_results=[simple_test_result],
        primitive=Label,
        search_engine=engine,
    )

    assert not [k for k in captured["config"] if k.startswith("search_engine.")]
