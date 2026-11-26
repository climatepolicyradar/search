"""Tests for the passages feeder's flow, from source record to sink record."""

from typing import Any

from vespa_feeder.passages.flow import passage_update


def _feed(record: dict[str, Any]) -> dict[str, Any]:
    return passage_update({"id": "passage-0", "vespa_update": record})


def test_passages_flow_feeds_the_upstream_update_as_is() -> None:
    """Fusion derives every field but the type flags, so the rest pass through untouched."""
    fields = {
        "document_id": {"assign": "doc-0"},
        "labels": {"assign": [{"id": "concept::Q1"}]},
        "concept_counts": {"assign": {"concept::Q1": 1}},
        "heading_text": {"assign": "Intro"},
    }
    update = {"update": "id:passages:passages::doc-0::0", "create": True, "fields": dict(fields)}
    record = _feed(update)

    assert (record["update"], record["create"]) == ("id:passages:passages::doc-0::0", True)
    assert {name: record["fields"][name] for name in fields} == fields


def test_passages_flow_sets_the_type_flags_from_content_and_pages() -> None:
    """
    The flags land on the record, and the detectors see the record's page numbers.

    Covers the wiring only - the rulesets themselves are tested in
    test_derived_data.py. A contents listing is used because it is the
    one detector that reads `pages`: on page 3 it fires, on page 42 the
    front-matter veto rejects it.
    """
    contents_listing = (
        "1. Acknowledgement 6\n"
        "2. About the Guideline 7\n"
        "2.1. Purpose of the Guideline 7\n"
        "2.2. Scope of the Guideline 8\n"
        "2.2.1. Applicability 8\n"
        "2.2.2. Exemption 9\n"
        "2.2.3. Precedence 9\n"
        "2.2.4. Reference Standards and green building rating programmes 10"
    )

    def flags(page_number: int) -> dict:
        record = _feed(
            {
                "fields": {
                    "document_id": {"assign": "doc-0"},
                    "content": {"assign": contents_listing},
                    "pages": {"assign": [{"number": page_number}]},
                }
            }
        )
        return {
            name: record["fields"][name]
            for name in (
                "looks_like_short_heading",
                "looks_like_table_of_contents",
                "looks_like_reference_list",
                "is_page_header_or_footer",
                "looks_like_demoted_section",
            )
        }

    assert flags(3) == {
        "looks_like_short_heading": {"assign": False},
        "looks_like_table_of_contents": {"assign": True},
        "looks_like_reference_list": {"assign": False},
        "is_page_header_or_footer": {"assign": False},
        "looks_like_demoted_section": {"assign": False},
    }
    assert flags(42)["looks_like_table_of_contents"] == {"assign": False}


def test_passages_flow_threads_content_type_into_reference_list() -> None:
    """
    `content_type` reaches `looks_like_reference_list`, not just `content`/`pages`.

    A bare-URL-only passage is the clearest demonstration: it can only ever be
    caught via the bare-locator shortcut, which is gated on content_type
    specifically because a bare URL in `pageFooter` is as often a document's own
    self-referential permalink as a genuine citation (see the docstring in
    `derived_data.py`). Same content, different content_type, different
    verdict - confirmed against a real row from
    `PRODUCTION.PUBLISHED.PIPELINE_DATA_IN_VESPA_PASSAGE_UPDATES_V1`, which shapes
    `content_type` as `{"assign": ...}` exactly like `content` and `pages` do.
    """
    bare_url_footnote = "89 http://www.um.edu.mt/ceer."

    def is_reference_list(content_type: str) -> bool:
        record = _feed(
            {
                "fields": {
                    "document_id": {"assign": "doc-0"},
                    "content": {"assign": bare_url_footnote},
                    "content_type": {"assign": content_type},
                }
            }
        )
        return record["fields"]["looks_like_reference_list"]["assign"]

    assert is_reference_list("footnote") is True
    assert is_reference_list("pageFooter") is False


def test_passages_flow_sets_is_page_header_or_footer_from_content_type() -> None:
    """`is_page_header_or_footer` reads `content_type` directly, not `content`/`pages`."""

    def is_page_header_or_footer(content_type: str) -> bool:
        record = _feed(
            {
                "fields": {
                    "document_id": {"assign": "doc-0"},
                    "content": {"assign": "some text"},
                    "content_type": {"assign": content_type},
                }
            }
        )
        return record["fields"]["is_page_header_or_footer"]["assign"]

    assert is_page_header_or_footer("pageHeader") is True
    assert is_page_header_or_footer("pageFooter") is True
    assert is_page_header_or_footer("Text") is False


def test_passages_flow_handles_a_record_with_no_pages() -> None:
    """Passages from HTML documents have no page data - the export omits `pages`."""
    record = _feed(
        {"fields": {"document_id": {"assign": "doc-0"}, "content": {"assign": "Hello"}}}
    )

    assert record["fields"]["looks_like_table_of_contents"] == {"assign": False}
