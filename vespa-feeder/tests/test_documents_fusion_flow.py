"""
Unit tests for turning a `fusion.published.vespa_documents` row into a Vespa update.

Unlike the legacy export, whose rows are already `{update, create, fields}`, a
Fusion row is one flat object keyed by column name, so the feeder has to build
the Vespa operation itself.
"""

import json
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
        "attributes_double": {},
        "attributes_string": {"created": "2021-03-05T00:00:00"},
        "attributes_boolean": {},
        "attributes_identifiers": {},
        "passages": [],
        "document_source": {
            "id": "doc-0",
            "labels": [{"value": {"id": "status::Principal"}}],
            "documents": [{"type": "member_of", "value": {"id": "collection-0"}}],
        },
        "attributes_published_date": 1614902400,
        "principal_id": "doc-0",
    }
    row.update(overrides)
    return row


def test_row_becomes_a_vespa_update_that_creates_the_document() -> None:
    record = derive_fusion_document_data(_row())

    assert record["update"] == "id:documents:documents::doc-0"
    assert record["create"] is True


def test_each_column_is_assigned_to_the_field_of_the_same_name() -> None:
    record = derive_fusion_document_data(_row())

    for column in (
        "id",
        "title",
        "description",
        "labels",
        "geographies",
        "concepts",
        "concept_counts",
        "attributes_double",
        "attributes_string",
        "attributes_boolean",
        "attributes_identifiers",
        "passages",
        "attributes_published_date",
        "principal_id",
    ):
        assert record["fields"][column] == {"assign": _row()[column]}, column


def test_unused_version_column_is_not_fed() -> None:
    """`version` is always null upstream; assigning null would only clear a field nothing sets."""
    record = derive_fusion_document_data(_row())

    assert "version" not in record["fields"]


def test_document_source_is_fed_as_a_json_string() -> None:
    """Fusion exports it as a nested object but the Vespa field is a string."""
    document_source = _row()["document_source"]

    record = derive_fusion_document_data(_row())

    assigned = record["fields"]["document_source"]["assign"]
    assert isinstance(assigned, str)
    assert json.loads(assigned) == document_source


def test_document_source_already_a_string_is_not_double_encoded() -> None:
    record = derive_fusion_document_data(_row(document_source='{"id": "doc-0"}'))

    assert record["fields"]["document_source"] == {"assign": '{"id": "doc-0"}'}


@pytest.mark.parametrize("column", ["title", "description"])
def test_control_characters_are_stripped_from_text(column: str) -> None:
    """
    Same characters the legacy export removed in SQL.

    Tab, newline and carriage return are kept; the rest of the C0 range goes.
    """
    record = derive_fusion_document_data(_row(**{column: "a\x00b\x07c\x0bd\x1fe\nf\tg\rh"}))

    assert record["fields"][column] == {"assign": "abcde\nf\tg\rh"}


def test_null_description_is_assigned_null() -> None:
    """Assigning null clears a description removed upstream, rather than leaving the old one."""
    record = derive_fusion_document_data(_row(description=None))

    assert record["fields"]["description"] == {"assign": None}


def test_principal_id_comes_from_the_row_not_from_document_source() -> None:
    """Fusion owns `principal_id`, so the legacy derivation from `document_source` must not override it."""
    record = derive_fusion_document_data(_row(principal_id="from-fusion"))

    assert record["fields"]["principal_id"] == {"assign": "from-fusion"}


def test_feeder_side_derivers_still_run() -> None:
    """`collection_id`, the hoisted attributes, `attributes_created_at` and `distinct_concept_ids` are not in Fusion."""
    record = derive_fusion_document_data(
        _row(
            attributes_string={
                "created": "2021-03-05T00:00:00",
                "deprecated_slug": "a-slug_0001",
                "last_updated_date": "2021-03-05T00:00:00Z",
            },
            concept_counts={"concept::Q2": 1, "concept::Q1": 3},
        )
    )

    assert record["fields"]["collection_id"] == {"assign": "collection-0"}
    assert record["fields"]["deprecated_slug"] == {"assign": "a-slug_0001"}
    assert record["fields"]["last_updated_date"] == {"assign": "2021-03-05T00:00:00Z"}
    assert record["fields"]["attributes_created_at"] == {"assign": 1614902400}
    assert record["fields"]["distinct_concept_ids"] == {
        "assign": ["concept::Q1", "concept::Q2"]
    }


def test_null_document_source_is_tolerated() -> None:
    """Nothing to derive a collection from, so `collection_id` is simply not set."""
    record = derive_fusion_document_data(_row(document_source=None))

    assert record["fields"]["document_source"] == {"assign": None}
    assert "collection_id" not in record["fields"]


def test_row_without_an_id_is_an_error() -> None:
    """An update with no id cannot be addressed; fail loudly rather than feed a bad document id."""
    row = _row()
    del row["id"]

    with pytest.raises(ValueError, match="id"):
        derive_fusion_document_data(row)
