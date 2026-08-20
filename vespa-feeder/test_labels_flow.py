"""Unit tests for the labels feeder's record derivers."""

import json

from labels_flow import derive_label_data, derive_label_source


def _record_with_relationships() -> dict:
    return {
        "fields": {
            "id": {"assign": "concept::Q1"},
            "type": {"assign": "concept"},
            "value": {"assign": "adaptation finance"},
            "labels": {
                "assign": [
                    {
                        "id": "concept::Q2",
                        "type": "concept",
                        "value": "finance",
                        "relationship": "subconcept_of",
                    }
                ]
            },
        }
    }


def test_derive_label_source_builds_flat_label_json() -> None:
    """label_source is a flat DataInLabel-shaped JSON string, built from id/type/value/labels."""
    record = derive_label_source(_record_with_relationships())

    label_source = json.loads(record["fields"]["label_source"]["assign"])
    assert label_source == {
        "id": "concept::Q1",
        "type": "concept",
        "value": "adaptation finance",
        "labels": [
            {
                "type": "subconcept_of",
                "value": {
                    "id": "concept::Q2",
                    "type": "concept",
                    "value": "finance",
                    "labels": [],
                },
                "timestamp": None,
            }
        ],
    }


def test_derive_label_source_handles_no_relationships() -> None:
    """A label with no `labels` field still gets a valid label_source with an empty list."""
    record = {
        "fields": {
            "id": {"assign": "geography::BRA"},
            "type": {"assign": "geography"},
            "value": {"assign": "Brazil"},
        }
    }

    record = derive_label_source(record)

    label_source = json.loads(record["fields"]["label_source"]["assign"])
    assert label_source == {
        "id": "geography::BRA",
        "type": "geography",
        "value": "Brazil",
        "labels": [],
    }


def test_derive_label_data_applies_deriver() -> None:
    """derive_label_data is the single entry point passed to vespa_feeder."""
    record = derive_label_data(_record_with_relationships())

    assert "label_source" in record["fields"]


def test_derive_label_source_skips_malformed_relationship_without_failing() -> None:
    """A malformed relationship entry is skipped, not fatal to the whole record."""
    record = {
        "fields": {
            "id": {"assign": "concept::Q1"},
            "type": {"assign": "concept"},
            "value": {"assign": "adaptation finance"},
            "labels": {
                "assign": [
                    {
                        "id": "concept::Q2",
                        "type": "concept",
                        "relationship": "subconcept_of",
                    },  # missing "value"
                    {
                        "id": "concept::Q3",
                        "type": "concept",
                        "value": "finance",
                        "relationship": "subconcept_of",
                    },
                ]
            },
        }
    }

    record = derive_label_source(record)

    label_source = json.loads(record["fields"]["label_source"]["assign"])
    assert label_source["id"] == "concept::Q1"
    assert len(label_source["labels"]) == 1
    assert label_source["labels"][0]["value"]["id"] == "concept::Q3"
