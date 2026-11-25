"""
Flow tests for turning a `fusion.published.vespa_documents` row into a Vespa update.

Unlike the legacy export, whose rows are already `{update, create, fields}`, a
Fusion row is one flat object keyed by column name, so the feeder has to build
the Vespa operation itself. Fusion owns every value, so that is all it does.
"""

from typing import Any

import pytest
from vespa_feeder.documents.flow import documents
from vespa_feeder.stream.stream import TransformFailures

from tests.stream.list_source import ListSource


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


def _feed(row: dict[str, Any]) -> list[dict[str, Any]]:
    return list(ListSource(items=[row]).chain(documents).lines())


def _row_without_an_id() -> dict[str, Any]:
    row = _row()
    del row["id"]
    return row


def test_row_becomes_a_vespa_update_that_creates_the_document() -> None:
    record = _feed(_row())[0]

    assert record["update"] == "id:documents:documents::doc-0"
    assert record["create"] is True


def test_each_column_is_assigned_as_is_to_the_field_of_the_same_name() -> None:
    row = _row()

    record = _feed(row)[0]

    assert record["fields"] == {
        column: {"assign": value}
        for column, value in row.items()
        if column != "version"
    }


def test_unused_version_column_is_not_fed() -> None:
    """`version` is always null upstream; assigning null would only clear a field nothing sets."""
    record = _feed(_row())[0]

    assert "version" not in record["fields"]


def test_null_value_is_assigned_null() -> None:
    """Assigning null clears a value removed upstream, rather than leaving the old one."""
    record = _feed(_row(description=None))[0]

    assert record["fields"]["description"] == {"assign": None}


def test_row_without_an_id_is_an_error() -> None:
    """An update with no id cannot be addressed; fail loudly rather than feed a bad document id."""
    row = _row()
    del row["id"]

    with pytest.raises(TransformFailures):
        _feed(row)


def test_rows_either_side_of_a_bad_row_are_still_fed() -> None:
    rows = [_row(id="a"), _row_without_an_id(), _row(id="b")]
    updates = ListSource(items=rows).chain(documents).lines()
    fed = [next(updates)["update"], next(updates)["update"]]
    assert fed == ["id:documents:documents::a", "id:documents:documents::b"]
    with pytest.raises(TransformFailures, match="1 records"):
        next(updates)


def test_five_hundred_bad_rows_are_tolerated_until_the_end() -> None:
    rows = [_row_without_an_id() for _ in range(500)] + [_row(id="a")]
    updates = ListSource(items=rows).chain(documents).lines()
    assert next(updates)["update"] == "id:documents:documents::a"
    with pytest.raises(TransformFailures, match="500 records"):
        next(updates)


def test_more_than_five_hundred_bad_rows_stop_the_feed() -> None:
    rows = [_row_without_an_id() for _ in range(501)] + [_row(id="a")]
    updates = ListSource(items=rows).chain(documents).lines()
    with pytest.raises(TransformFailures, match="501 records"):
        next(updates)
