"""
Unit tests for ``labels_feed_materializer``.

Regression coverage for the ``label_source`` round-trip: the labels search
engine parses ``label_source`` as a flat :class:`DataInLabel`, so the
materialiser must store it in the same shape.
"""

from cpr_contracts import DocumentLabelRelationship, Label

from search.data_in_models import Label as DataInLabel
from search.vespa.labels_feed_materializer import (
    _source_label_relationship_to_vespa_label,
    _wikibase_concept_to_vespa_label,
)
from search.vespa.sources.wikibase import (
    WikibaseConcept,
    _compute_label_relationships,
)


def test_source_label_relationship_to_vespa_label_label_source_round_trips() -> None:
    """
    Check label_source structure is correct.

    ``label_source`` must parse as :class:`DataInLabel` (flat ``id``/``type``/
    ``value``). If the materialiser writes a relationship envelope instead, the
    search engine drops every document-derived label at read time with a
    "Label source is invalid" warning and returns zero results.
    """
    label_rel: DocumentLabelRelationship = DocumentLabelRelationship(
        type="related",
        value=Label(
            id="principal_law::Bavaria Climate Protection Act",
            type="principal_law",
            value="Bavaria Climate Protection Act",
            labels=[]
        ),
        timestamp= None,
    )

    vespa_label = _source_label_relationship_to_vespa_label(label_rel)

    parsed = DataInLabel.model_validate_json(vespa_label["label_source"])
    assert parsed.id == "principal_law::Bavaria Climate Protection Act"
    assert parsed.type == "principal_law"
    assert parsed.value == "Bavaria Climate Protection Act"




def test_wikibase_concept_to_vespa_label_returns_vespa_label_shape() -> None:
    concept: WikibaseConcept = {
        "wikibase_id": "Q123",
        "preferred_label": "Climate adaptation",
        "alternative_labels": ["Adaptation"],
        "description": "A concept",
        "negative_labels": [],
        "subconcept_labels": [],
        "label_relationships": [],
    }
    vespa_label = _wikibase_concept_to_vespa_label(concept)
    assert vespa_label["id"] == "concept::Q123"
    assert vespa_label["type"] == "concept"
    parsed = DataInLabel.model_validate_json(vespa_label["label_source"])
    assert parsed.id == "concept::Q123"
    assert parsed.value == "Climate adaptation"


def test_wikibase_concept_to_vespa_label_propagates_label_relationships() -> None:
    """
    Regression for APP-2185: wikibase labels had ``labels`` hardcoded to ``[]``.

    When a WikibaseConcept has label_relationships (e.g. it is a subconcept of
    another concept), those relationships must appear in both:
    - ``vespa_label["labels"]`` (used for Vespa hierarchical filtering)
    - the ``label_source`` JSON (parsed as DataInLabel by the search engine)
    """
    concept: WikibaseConcept = {
        "wikibase_id": "Q456",
        "preferred_label": "Renewable Energy",
        "alternative_labels": [],
        "description": None,
        "negative_labels": [],
        "subconcept_labels": [],
        "label_relationships": [
            {
                "wikibase_id": "Q123",
                "preferred_label": "Energy",
                "relationship_type": "subconcept_of",
            }
        ],
    }

    vespa_label = _wikibase_concept_to_vespa_label(concept)

    assert len(vespa_label["labels"]) == 1
    assert vespa_label["labels"][0] == {
        "id": "concept::Q123",
        "type": "concept",
        "value": "Energy",
        "timestamp": None,
        "relationship": "subconcept_of",
    }

    parsed = DataInLabel.model_validate_json(vespa_label["label_source"])
    assert parsed.id == "concept::Q456"
    assert len(parsed.labels) == 1
    assert parsed.labels[0].type == "subconcept_of"


def test_compute_label_relationships_derives_direct_parents() -> None:
    """
    _compute_label_relationships returns the direct parent for each concept.

    Given: Energy (Q1) → Renewable Energy (Q2) → Solar Energy (Q3)
    (each arrow meaning "has subconcept")

    Q3 should have Q2 as direct parent (not Q1, which is a transitive ancestor).
    Q2 should have Q1 as direct parent.
    """
    wid_to_subconcept_ids: dict[str, list[str]] = {
        "Q1": ["Q2", "Q3"],  # Energy has subconcepts Renewable Energy and Solar Energy
        "Q2": ["Q3"],  # Renewable Energy has subconcept Solar Energy
    }
    concept_by_wid: dict[str, WikibaseConcept] = {
        "Q1": {
            "wikibase_id": "Q1",
            "preferred_label": "Energy",
            "alternative_labels": [],
            "description": None,
            "negative_labels": [],
            "subconcept_labels": [],
            "label_relationships": [],
        },
        "Q2": {
            "wikibase_id": "Q2",
            "preferred_label": "Renewable Energy",
            "alternative_labels": [],
            "description": None,
            "negative_labels": [],
            "subconcept_labels": [],
            "label_relationships": [],
        },
    }

    result = _compute_label_relationships(wid_to_subconcept_ids, concept_by_wid)

    # Q2 (Renewable Energy) is a direct subconcept_of Q1 (Energy)
    assert result["Q2"] == [
        {"wikibase_id": "Q1", "preferred_label": "Energy", "relationship_type": "subconcept_of"}
    ]
    # Q3 (Solar Energy) is a direct subconcept_of Q2 (Renewable Energy), not Q1
    assert result["Q3"] == [
        {"wikibase_id": "Q2", "preferred_label": "Renewable Energy", "relationship_type": "subconcept_of"}
    ]
    # Q1 has no parents
    assert "Q1" not in result
