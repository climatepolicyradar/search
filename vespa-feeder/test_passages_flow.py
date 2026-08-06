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
