"""
Unit tests for turning a `fusion.published.vespa_documents` row into a Vespa update.

Unlike the legacy export, whose rows are already `{update, create, fields}`, a
Fusion row is one flat object keyed by column name, so the feeder has to build
the Vespa operation itself. Fusion owns every value, so that is all it does.
"""

from typing import Any

import pytest
from documents_flow import derive_fusion_document_data


def _row(**overrides: Any) -> dict[str, Any]:
    """A Fusion `vespa_documents` row, with every column present."""
    row: dict[str, Any] = {
        "version": None,
        "id": "doc-0",
        "title": "A title",
        "description": "A description",
        "labels": [
            {
                "id": "geography::GBR",
                "type": "geography",
                "value": "United Kingdom",
                "relationship": "geography",
                "timestamp": None,
            }
        ],
        "geographies": ["United Kingdom"],
        "concepts": [{"id": "concept::Q1", "type": "concept", "value": "finance"}],
        "concept_counts": {"concept::Q1": 3},
        "distinct_concept_ids": ["concept::Q1"],
        "attributes_double": {},
        "attributes_string": {"created": "2021-03-05T00:00:00Z"},
        "attributes_boolean": {},
        "attributes_identifiers": {},
        "passages": [],
        "deprecated_slug": "a-slug_0001",
        "last_updated_date": "2021-03-05T00:00:00Z",
        "document_source": '{"id":"doc-0"}',
        "attributes_published_date": 1614902400,
        "attributes_created_at": 1614902400,
        "principal_id": "doc-0",
        "collection_id": "collection-0",
    }
    row.update(overrides)
    return row


def test_row_becomes_a_vespa_update_that_creates_the_document() -> None:
    record = derive_fusion_document_data(_row())

    assert record["update"] == "id:documents:documents::doc-0"
    assert record["create"] is True


def test_each_column_is_assigned_as_is_to_the_field_of_the_same_name() -> None:
    row = _row()

    record = derive_fusion_document_data(row)

    assert record["fields"] == {
        column: {"assign": value}
        for column, value in row.items()
        if column != "version"
    }


def test_unused_version_column_is_not_fed() -> None:
    """`version` is always null upstream; assigning null would only clear a field nothing sets."""
    record = derive_fusion_document_data(_row())

    assert "version" not in record["fields"]


def test_null_value_is_assigned_null() -> None:
    """Assigning null clears a value removed upstream, rather than leaving the old one."""
    record = derive_fusion_document_data(_row(description=None))

    assert record["fields"]["description"] == {"assign": None}


def test_row_without_an_id_is_an_error() -> None:
    """An update with no id cannot be addressed; fail loudly rather than feed a bad document id."""
    row = _row()
    del row["id"]

    with pytest.raises(ValueError, match="id"):
        derive_fusion_document_data(row)
