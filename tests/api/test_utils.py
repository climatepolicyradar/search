"""Tests for ``api.utils`` dependency functions."""

from api.utils import passages_engine
from search.engines.dev_vespa.passages_search_engine import (
    _DEFAULT_PASSAGE_RANK_PROFILE,
)


def test_passages_engine_default_rank() -> None:
    engine = passages_engine(rank=None)

    assert engine.ranking_profile == _DEFAULT_PASSAGE_RANK_PROFILE


def test_passages_engine_with_rank() -> None:
    engine = passages_engine(rank="unranked")

    assert engine.ranking_profile == "unranked"
