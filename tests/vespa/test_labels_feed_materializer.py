"""
Unit tests for ``labels_feed_materializer``.

Regression coverage for the ``label_source`` round-trip: the labels search
engine parses ``label_source`` as a flat :class:`DataInLabel`, so the
materialiser must store it in the same shape.
"""

from search.data_in_models import Label as DataInLabel
from search.vespa.labels_feed_materializer import (
    _label_source_json,
    _source_label_relationship_to_vespa_label,
    _wikibase_concept_to_vespa_label,
)
from search.vespa.sources.data_in_api import SourceLabel, SourceLabelRelationship
from search.vespa.sources.wikibase import WikibaseConcept


def test_source_label_relationship_to_vespa_label_label_source_round_trips() -> None:
    """
    Check label_source structure is correct.

    ``label_source`` must parse as :class:`DataInLabel` (flat ``id``/``type``/
    ``value``). If the materialiser writes a relationship envelope instead, the
    search engine drops every document-derived label at read time with a
    "Label source is invalid" warning and returns zero results.
    """
    label_rel: SourceLabelRelationship = {
        "type": "related",
        "value": SourceLabel(
            id="principal_law::Bavaria Climate Protection Act",
            type="principal_law",
            value="Bavaria Climate Protection Act",
        ),
        "timestamp": None,
    }

    vespa_label = _source_label_relationship_to_vespa_label(label_rel)

    parsed = DataInLabel.model_validate_json(vespa_label["label_source"])
    assert parsed.id == "principal_law::Bavaria Climate Protection Act"
    assert parsed.type == "principal_law"
    assert parsed.value == "Bavaria Climate Protection Act"


def test_label_source_json_accepts_flat_source_label_only() -> None:
    """``_label_source_json`` must take ``SourceLabel``, not the relationship envelope."""
    source_label: SourceLabel = {
        "id": "geography::BR-AM",
        "type": "geography",
        "value": "Amazonas",
    }
    parsed = DataInLabel.model_validate_json(_label_source_json(source_label))
    assert parsed.id == "geography::BR-AM"
    assert parsed.type == "geography"
    assert parsed.value == "Amazonas"


def test_wikibase_concept_to_vespa_label_returns_vespa_label_shape() -> None:
    concept: WikibaseConcept = {
        "wikibase_id": "Q123",
        "preferred_label": "Climate adaptation",
        "alternative_labels": ["Adaptation"],
        "description": "A concept",
        "negative_labels": [],
        "subconcept_labels": [],
    }
    vespa_label = _wikibase_concept_to_vespa_label(concept)
    assert vespa_label["id"] == "concept::Q123"
    assert vespa_label["type"] == "concept"
    parsed = DataInLabel.model_validate_json(vespa_label["label_source"])
    assert parsed.id == "concept::Q123"
    assert parsed.value == "Climate adaptation"
