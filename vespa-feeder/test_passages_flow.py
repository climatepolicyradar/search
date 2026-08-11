"""Unit tests for the passages feeder's record derivers."""

from passages_flow import derive_passage_data


def _record_with_topics() -> dict:
    return {
        "fields": {
            "document_id": {"assign": "doc-0"},
            "topics": {
                "assign": [
                    {
                        "id": "topic-1",
                        "concept_id": "finance flow",
                        "classifier_id": "classifier-1",
                        "end_index": 12,
                        "labelled_text": "finance flow",
                        "labellers": ['BertBasedClassifier("finance flow")'],
                        "prediction_probability": 0.9,
                        "start_index": 0,
                        "timestamps": ["2024-01-01T00:00:00"],
                        "value": "finance flow",
                    }
                ]
            },
        }
    }


def test_derive_passage_data_derives_labels_and_document_ref() -> None:
    """Both derivers apply: topics become labels, and document_ref is set from document_id."""
    record = derive_passage_data(_record_with_topics())

    assert record["fields"]["document_ref"] == {
        "assign": "id:documents:documents::doc-0"
    }
    assert record["fields"]["labels"] == {
        "assign": [
            {
                "id": "concept::finance flow",
                "type": "concept",
                "value": "finance flow",
                "classifier_id": "classifier-1",
                "end_index": 12,
                "labelled_text": "finance flow",
                "labellers": ['BertBasedClassifier("finance flow")'],
                "prediction_probability": 0.9,
                "start_index": 0,
                "timestamps": ["2024-01-01T00:00:00"],
            }
        ]
    }
    assert "topics" not in record["fields"]


def test_derive_passage_data_sets_the_type_flags_from_content_and_pages() -> None:
    """
    The flags land on the record, and the detectors see the record's page numbers.

    Covers the wiring only - the rulesets themselves are tested in
    test_passages_derived_data.py. A contents listing is used because it is the
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
        record = derive_passage_data(
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
            )
        }

    assert flags(3) == {
        "looks_like_short_heading": {"assign": False},
        "looks_like_table_of_contents": {"assign": True},
        "looks_like_reference_list": {"assign": False},
    }
    assert flags(42)["looks_like_table_of_contents"] == {"assign": False}


def test_derive_passage_data_handles_a_record_with_no_pages() -> None:
    """Passages from HTML documents have no page data - the export omits `pages`."""
    record = derive_passage_data(
        {"fields": {"document_id": {"assign": "doc-0"}, "content": {"assign": "Hello"}}}
    )

    assert record["fields"]["looks_like_table_of_contents"] == {"assign": False}
