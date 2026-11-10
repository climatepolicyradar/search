"""Unit tests for the documents feeder's record derivers."""

import json
from typing import Any

from documents_flow import derive_collection_id, derive_hoisted_attributes


def _record(attributes: dict[str, str]) -> dict[str, Any]:
    return {
        "create": True,
        "update": "id:documents:documents::doc-0",
        "fields": {"attributes_string": {"assign": attributes}},
    }


def test_hoists_both_keys_out_of_attributes_string() -> None:
    record: dict[str, Any] = derive_hoisted_attributes(
        _record(
            {
                "deprecated_slug": "planning-act-2008-1e9d",
                "last_updated_date": "2021-03-05T00:00:00Z",
                "md5_sum": "ac36417dfae421df85927a2213c5cdb4",
            }
        )
    )

    assert record["fields"]["deprecated_slug"] == {"assign": "planning-act-2008-1e9d"}
    assert record["fields"]["last_updated_date"] == {
        "assign": "2021-03-05T00:00:00Z"
    }


def test_leaves_other_attributes_where_they_are() -> None:
    """Hoisting copies, so filters and `document_source` keep working unchanged."""
    input_record = _record({"deprecated_slug": "a-slug_0001", "md5_sum": "abc"})
    record = derive_hoisted_attributes(input_record)

    assert record["fields"]["attributes_string"]["assign"] == {
        "deprecated_slug": "a-slug_0001",
        "md5_sum": "abc",
    }


def test_absent_key_is_assigned_empty() -> None:
    """
    A key missing from `attributes_string` clears the hoisted field.

    Updates replace `attributes_string` wholesale but leave unmentioned fields
    alone, so only assigning on presence would let a slug dropped upstream live
    on in the hoisted copy - and the sitemap would keep emitting its dead URL.
    Vespa stores no null for strings, so "" reads back the same as never set.
    """
    record = derive_hoisted_attributes(_record({"last_updated_date": "2021-03-05T00:00:00Z"}))
    assert record["fields"]["deprecated_slug"] == {"assign": ""}


def test_record_without_attributes_string_is_unchanged() -> None:
    record = derive_hoisted_attributes({"update": "id:documents:documents::doc-0", "fields": {}})
    assert record["fields"] == {}


def _source_record(document_source: dict[str, Any]) -> dict[str, Any]:
    return {
        "create": True,
        "update": "id:documents:documents::doc-0",
        "fields": {"document_source": {"assign": json.dumps(document_source)}},
    }


def _principal(id: str, relationships: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": id,
        "labels": [{"value": {"id": "status::Principal"}}],
        "documents": relationships,
    }


def _member_of(target: str) -> dict[str, Any]:
    return {"type": "member_of", "value": {"id": target}}


def test_principal_takes_the_collection_it_is_a_member_of() -> None:
    record: dict[str, Any] = derive_collection_id(
        _source_record(
            _principal("Sabin.family.19829.0", [_member_of("Sabin.collection.19831.0")])
        )
    )

    assert record["fields"]["collection_id"] == {"assign": "Sabin.collection.19831.0"}


def test_principal_without_a_collection_has_no_collection_id() -> None:
    """Absent, not empty - a blank cell and "no collection" are the same thing here."""
    record: dict[str, Any] = derive_collection_id(
        _source_record(_principal("Sabin.family.1.0", []))
    )

    assert "collection_id" not in record["fields"]


def test_non_principal_member_of_its_family_has_no_collection_id() -> None:
    """
    `member_of` names a family for a non-Principal, and a collection for a Principal.

    Filling `collection_id` from it either way would put a family id in a field
    that otherwise holds collection ids.
    """
    document_source: dict[str, Any] = {
        "id": "Sabin.document.12835.14111",
        "labels": [{"value": {"id": "status::Published"}}],
        "documents": [_member_of("Sabin.family.12835.0")],
    }

    record: dict[str, Any] = derive_collection_id(_source_record(document_source))

    assert "collection_id" not in record["fields"]


def test_is_version_of_is_not_a_collection() -> None:
    document_source: dict[str, Any] = _principal(
        "CCLW.family.9987.0",
        [{"type": "is_version_of", "value": {"id": "CCLW.family.9987.0"}}],
    )

    record: dict[str, Any] = derive_collection_id(_source_record(document_source))

    assert "collection_id" not in record["fields"]


def test_principal_in_several_collections_takes_the_first() -> None:
    record: dict[str, Any] = derive_collection_id(
        _source_record(
            _principal(
                "Sabin.family.2.0",
                [_member_of("Sabin.collection.1.0"), _member_of("Sabin.collection.2.0")],
            )
        )
    )

    assert record["fields"]["collection_id"] == {"assign": "Sabin.collection.1.0"}


def test_record_without_document_source_is_unchanged() -> None:
    input_record: dict[str, Any] = {"create": True, "fields": {}}

    assert derive_collection_id(input_record) == {"create": True, "fields": {}}
