"""Unit tests for ``documents_feed_materializer``."""

from cpr_contracts import Document

from search.vespa.documents_feed_materializer import _source_document_to_vespa_update


def _document(attributes: dict[str, str | float | bool]) -> Document:
    return Document(id="doc-0", title="A document", labels=[], documents=[], attributes=attributes)


def test_created_is_set_as_epoch_seconds() -> None:
    update = _source_document_to_vespa_update(_document({"created": "2019-05-01T09:00:00Z"}))
    assert update["fields"].get("attributes_created_at") == {"assign": 1556701200}


def test_created_without_a_timezone_is_read_as_utc() -> None:
    """RDS timestamps arrive naive (e.g. `2023-02-03T04:05:06.789000`) and are UTC."""
    update = _source_document_to_vespa_update(_document({"created": "2023-02-03T04:05:06.789000"}))
    assert update["fields"].get("attributes_created_at") == {"assign": 1675397106}


def test_missing_or_unparsable_created_is_not_assigned() -> None:
    """Leaving the field unset sorts the document last, rather than at 1970."""
    cases: list[dict[str, str | float | bool]] = [{}, {"created": ""}, {"created": "not-a-date"}]
    for attributes in cases:
        update = _source_document_to_vespa_update(_document(attributes))
        assert "attributes_created_at" not in update["fields"]
