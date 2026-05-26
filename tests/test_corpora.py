"""Unit tests for corpus -> Vespa filter construction."""

from search.corpora import CORPUS_PROVIDERS, build_corpus_filter
from search.engines.dev_vespa import FieldFilter, _build_filter_yql


def test_ccc_corpus_filter_targets_sabin_only() -> None:
    """The ccc corpus has a single provider, so the filter is a single clause."""
    filter_ = build_corpus_filter("ccc")
    yql = _build_filter_yql(filter_)
    # `labels.value.id` is mapped to both `labels.id` and `concepts.id` by
    # the existing field map (see filter_field_to_vespa_field_map). The
    # concepts.id clause is harmless because concept IDs never start with
    # "agent::".
    assert yql == (
        '(labels.id contains "agent::Sabin Center for Climate Change Law" '
        'or concepts.id contains "agent::Sabin Center for Climate Change Law")'
    )


def test_corpus_filter_or_joins_providers() -> None:
    """Filters for a multi-provider corpus OR together one clause per provider."""
    filter_ = build_corpus_filter("mcf")
    assert filter_.op == "or"
    assert len(filter_.filters) == len(CORPUS_PROVIDERS["mcf"])
    for condition, provider in zip(filter_.filters, CORPUS_PROVIDERS["mcf"]):
        assert isinstance(condition, FieldFilter)
        assert condition.field == "labels.value.id"
        assert condition.op == "contains"
        assert condition.value == f"agent::{provider}"
