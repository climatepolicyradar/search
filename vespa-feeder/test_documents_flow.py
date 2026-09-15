"""Unit tests for the documents feeder's concept deriver."""

from documents_flow import derive_concepts_from_labels, derive_document_data


def _concept_edge(bare_id: str, count: int, value: str) -> dict:
    """
    A `type="concept"` label edge, as the data-lake export emits them.

    Concept edges arrive with a bare wikibase id, a non-null mention `count`,
    a v2 passage-uuid `passages_id`, and a null `relationship` - verified
    against `PRODUCTION.PUBLISHED.PIPELINE_DATA_IN_VESPA_DOCUMENTS_V1`.
    """
    return {
        "id": bare_id,
        "type": "concept",
        "value": value,
        "count": count,
        "passages_id": "019cda32-a684-79e1-b70b-e10cfe29ad52",
        "relationship": None,
        "timestamp": None,
    }


def _non_concept_edge() -> dict:
    """A non-concept edge (null count, has a relationship) - must be ignored."""
    return {
        "id": "entity_type::Corporate voluntary filing",
        "type": "entity_type",
        "value": "Corporate voluntary filing",
        "count": None,
        "passages_id": None,
        "relationship": "entity_type",
        "timestamp": None,
    }


def test_rebuilds_concepts_and_counts_from_concept_labels() -> None:
    """Concept edges become `concepts` (ids prefixed) + `concept_counts`; others ignored."""
    record = derive_concepts_from_labels(
        {
            "fields": {
                "labels": {
                    "assign": [
                        _concept_edge("Q1829", 4, "finance flow"),
                        _concept_edge("Q638", 1, "energy"),
                        _non_concept_edge(),
                    ]
                }
            }
        }
    )

    assert record["fields"]["concepts"] == {
        "assign": [
            {
                "id": "concept::Q1829",
                "type": "concept",
                "value": "finance flow",
                "count": 4,
                "passages_id": "019cda32-a684-79e1-b70b-e10cfe29ad52",
            },
            {
                "id": "concept::Q638",
                "type": "concept",
                "value": "energy",
                "count": 1,
                "passages_id": "019cda32-a684-79e1-b70b-e10cfe29ad52",
            },
        ]
    }
    assert record["fields"]["concept_counts"] == {
        "assign": {"concept::Q1829": 4, "concept::Q638": 1}
    }


def test_overrides_stale_concepts_carried_in_the_export() -> None:
    """The stale `concepts`/`concept_counts` from the export are replaced, not merged."""
    record = derive_concepts_from_labels(
        {
            "fields": {
                "labels": {"assign": [_concept_edge("Q638", 1, "energy")]},
                "concepts": {
                    "assign": [
                        {
                            "id": "concept::Q1829",
                            "type": "concept",
                            "value": "finance flow",
                            "count": 4891,
                            "passages_id": None,
                        }
                    ]
                },
                "concept_counts": {"assign": {"concept::Q1829": 4891}},
            }
        }
    )

    assert record["fields"]["concept_counts"] == {"assign": {"concept::Q638": 1}}
    assert [c["id"] for c in record["fields"]["concepts"]["assign"]] == [
        "concept::Q638"
    ]


def test_orphan_with_no_concept_edges_gets_empty_concepts() -> None:
    """
    A document whose `labels` carry no concept edges is emptied, not left stale.

    This is the exact FUS-310 orphan (a principal with a fossilised concept
    count but no v2 passages): emptying `concepts` drops it from the
    `concepts.id` filter and zeroes its `topic_score`.
    """
    record = derive_concepts_from_labels(
        {"fields": {"labels": {"assign": [_non_concept_edge()]}}}
    )

    assert record["fields"]["concepts"] == {"assign": []}
    assert record["fields"]["concept_counts"] == {"assign": {}}


def test_partial_update_without_labels_is_left_untouched() -> None:
    """A record that does not carry `labels` must not have its concepts wiped."""
    record = derive_concepts_from_labels({"fields": {"id": {"assign": "doc-0"}}})

    assert "concepts" not in record["fields"]
    assert "concept_counts" not in record["fields"]


def test_already_prefixed_concept_id_is_not_double_prefixed() -> None:
    """Defensive: an id already carrying the `concept::` prefix is left as-is."""
    record = derive_concepts_from_labels(
        {"fields": {"labels": {"assign": [_concept_edge("concept::Q1", 2, "x")]}}}
    )

    assert record["fields"]["concept_counts"] == {"assign": {"concept::Q1": 2}}


def test_derive_document_data_applies_the_concept_override() -> None:
    """The override runs in the full chain, alongside principal_id / id derivation."""
    record = derive_document_data(
        {"fields": {"labels": {"assign": [_concept_edge("Q1829", 3, "finance flow")]}}}
    )

    assert record["fields"]["concept_counts"] == {"assign": {"concept::Q1829": 3}}