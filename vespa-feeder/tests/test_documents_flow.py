"""Unit tests for the documents feeder's record derivers."""

from typing import Any

from documents_flow import derive_hoisted_attributes


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
