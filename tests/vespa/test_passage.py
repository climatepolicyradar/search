"""Unit tests for the canonical `VespaPassage` model."""

from search.vespa.passage import (
    VespaBoundingBox,
    VespaCoordinate,
    VespaLabel,
    VespaPageBoxes,
    VespaPassage,
)


def test_model_validate_tolerates_empty_dict() -> None:
    """An empty hit `fields` dict validates to all-default values, not an error."""
    passage = VespaPassage.model_validate({})

    assert passage.id == ""
    assert passage.content == ""
    assert passage.pages == []
    assert passage.labels == []
    assert passage.tokens == []


def test_model_validate_ignores_unknown_raw_hit_fields() -> None:
    """Raw Vespa hit fields not on the model (sddocname, summaryfeatures, ...) are ignored."""
    passage = VespaPassage.model_validate(
        {"id": "block-0", "sddocname": "passages", "summaryfeatures": {"foo": 1.0}}
    )

    assert passage.id == "block-0"


def test_tokens_flattens_dict_shaped_text_tokens() -> None:
    """The debug-summary `{"values": [...]}` shape flattens, including nested stem lists."""
    passage = VespaPassage.model_validate(
        {"text_tokens": {"values": ["run", ["walk", "walking"]]}}
    )

    assert passage.tokens == ["run", "walk", "walking"]


def test_tokens_flattens_list_shaped_text_tokens() -> None:
    """A plain list shape (no `values` wrapper) also flattens."""
    passage = VespaPassage.model_validate({"text_tokens": ["run", ["walk", "walking"]]})

    assert passage.tokens == ["run", "walk", "walking"]


def test_tokens_defaults_to_empty_list_when_absent() -> None:
    passage = VespaPassage.model_validate({})

    assert passage.tokens == []


def test_to_vespa_update_raises_without_document_ref() -> None:
    """A passage with no document_ref can't be fed - it's a required schema field."""
    passage = VespaPassage(id="block-0")

    try:
        passage.to_vespa_update()
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when document_ref is unset")


def test_to_vespa_update_includes_required_fields() -> None:
    passage = VespaPassage(
        id="block-0",
        idx=0,
        language="en",
        content="some text",
        document_id="doc-0",
        document_ref="id:documents:documents::doc-0",
    )

    update = passage.to_vespa_update()

    assert update == {
        "update": "id:passages:passages::block-0",
        "create": True,
        "fields": {
            "id": {"assign": "block-0"},
            "idx": {"assign": 0},
            "language": {"assign": "en"},
            "content": {"assign": "some text"},
            "looks_like_short_heading": {"assign": False},
            "looks_like_table_of_contents": {"assign": False},
            "looks_like_reference_list": {"assign": False},
            "is_page_header_or_footer": {"assign": False},
            "looks_like_demoted_section": {"assign": False},
            "document_id": {"assign": "doc-0"},
            "document_ref": {"assign": "id:documents:documents::doc-0"},
        },
    }


def test_to_vespa_update_omits_unset_optional_fields() -> None:
    """Optional fields left at their default are omitted, not assigned as empty."""
    passage = VespaPassage(
        id="block-0",
        document_id="doc-0",
        document_ref="id:documents:documents::doc-0",
    )

    fields = passage.to_vespa_update()["fields"]

    for key in (
        "principal_document_ref",
        "content_type",
        "type_confidence",
        "heading_id",
        "heading_text",
        "labels",
        "pages",
    ):
        assert key not in fields


def test_to_vespa_update_includes_optional_fields_when_set() -> None:
    passage = VespaPassage(
        id="block-0",
        document_id="doc-0",
        document_ref="id:documents:documents::doc-0",
        principal_document_ref="id:documents:documents::principal-0",
        content_type="Text",
        type_confidence=0.9,
        heading_id="heading-1",
        heading_text="Chapter 1",
        labels=[
            VespaLabel(
                id="concept::finance flow",
                type="concept",
                value="finance flow",
                classifier_id="classifier-1",
                end_index=12.0,
                labelled_text="finance flow",
                labellers=["classifier-1"],
                prediction_probability=0.9,
                start_index=0.0,
                timestamps=["2024-01-01T00:00:00"],
            )
        ],
        pages=[
            VespaPageBoxes(
                number=3,
                bounding_boxes=[
                    VespaBoundingBox(coordinates=[VespaCoordinate(x=0.1, y=0.2)])
                ],
            )
        ],
    )

    fields = passage.to_vespa_update()["fields"]

    assert fields.get("principal_document_ref") == {
        "assign": "id:documents:documents::principal-0"
    }
    assert fields.get("content_type") == {"assign": "Text"}
    assert fields.get("type_confidence") == {"assign": 0.9}
    assert fields.get("heading_id") == {"assign": "heading-1"}
    assert fields.get("heading_text") == {"assign": "Chapter 1"}
    assert fields.get("labels") == {
        "assign": [
            {
                "id": "concept::finance flow",
                "type": "concept",
                "value": "finance flow",
                "classifier_id": "classifier-1",
                "end_index": 12.0,
                "labelled_text": "finance flow",
                "labellers": ["classifier-1"],
                "prediction_probability": 0.9,
                "start_index": 0.0,
                "timestamps": ["2024-01-01T00:00:00"],
            }
        ]
    }
    assert fields.get("pages") == {
        "assign": [
            {
                "number": 3,
                "bounding_boxes": [{"coordinates": [{"x": 0.1, "y": 0.2}]}],
            }
        ]
    }


def test_to_vespa_update_fields_are_plain_dicts_not_models() -> None:
    """Nested labels/pages must be plain dicts so orjson.dumps can serialize the update."""
    passage = VespaPassage(
        id="block-0",
        document_id="doc-0",
        document_ref="id:documents:documents::doc-0",
        labels=[
            VespaLabel(
                id="concept::finance flow",
                type="concept",
                value="finance flow",
                classifier_id="classifier-1",
                end_index=12.0,
                labelled_text="finance flow",
                labellers=["classifier-1"],
                prediction_probability=0.9,
                start_index=0.0,
                timestamps=["2024-01-01T00:00:00"],
            )
        ],
    )

    fields = passage.to_vespa_update()["fields"]
    labels = fields.get("labels")
    assert labels is not None

    assert isinstance(labels["assign"][0], dict)
