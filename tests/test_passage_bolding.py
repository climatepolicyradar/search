import pytest

from search.bolding import bolding_to_labels, merge_bolded, render_bolded
from search.passage import Passage
from search.vespa.passage import VespaPassage


@pytest.mark.parametrize(
    ("bolded_text", "expected_text", "expected_boldings"),
    [
        pytest.param("no bolding here", "no bolding here", [], id="no-tags"),
        pytest.param(
            "How is this Activity classified in an <hi>Insurance</hi> Company?",
            "How is this Activity classified in an Insurance Company?",
            [(38, 47, "Insurance")],
            id="one-bolding",
        ),
        pytest.param(
            "<hi>Carbon</hi> budgets for crude <hi>emissions</hi>.",
            "Carbon budgets for crude emissions.",
            [(0, 6, "Carbon"), (25, 34, "emissions")],
            id="two-boldings",
        ),
        pytest.param(
            "<hi>Carbon</hi> <hi>budget</hi>",
            "Carbon budget",
            [(0, 6, "Carbon"), (7, 13, "budget")],
            id="adjacent-boldings",
        ),
    ],
)
def test_bolding_to_labels_indexes_the_untagged_text(
    bolded_text: str,
    expected_text: str,
    expected_boldings: list[tuple[int, int, str]],
) -> None:
    """Indices relate to the tag-free text, because that is what the client is sent."""
    bolded = bolding_to_labels(bolded_text)

    assert bolded.text == expected_text
    assert [
        (h.start_index, h.end_index, h.labelled_text) for h in bolded.boldings
    ] == expected_boldings

    # The invariant behind those numbers: the offsets slice the bolded term
    # back out of the very text the client receives.
    for bolding in bolded.boldings:
        assert (
            bolded.text[bolding.start_index : bolding.end_index]
            == bolding.labelled_text
        )


def test_from_vespa_passage_leaves_text_alone_when_bolding_is_off() -> None:
    """
    Without `bolding`, `<hi>` in the source document is text, not Vespa markup.

    Vespa only wraps terms when asked, so anything tag-shaped in an unbolded
    response came from the document itself and must survive untouched.
    """
    vespa_passage = VespaPassage.model_validate(
        {"id": "tb-0", "content": "a <hi>literal</hi> tag", "document_id": "doc-0"}
    )

    passage = Passage.from_vespa_passage(vespa_passage)

    assert passage.text == "a <hi>literal</hi> tag"
    assert passage.boldings == []


def test_from_vespa_passage_strips_tags_and_records_spans_when_bolding_is_on() -> None:
    """With `bolding`, `text` is tag-free and the spans index into it."""
    vespa_passage = VespaPassage.model_validate(
        {
            "id": "tb-0",
            "content": "The <hi>carbon</hi> budget for crude <hi>emissions</hi>.",
            "document_id": "doc-0",
        }
    )

    passage = Passage.from_vespa_passage(vespa_passage, bolding=True)

    assert passage.text == "The carbon budget for crude emissions."
    assert [
        (h.start_index, h.end_index, h.labelled_text) for h in passage.boldings
    ] == [(4, 10, "carbon"), (28, 37, "emissions")]


@pytest.mark.parametrize(
    ("bolded_texts", "expected_boldings"),
    [
        pytest.param(
            [
                "<hi>Brazil</hi> plans a carbon tax.",
                "Brazil plans a <hi>carbon</hi> <hi>tax</hi>.",
            ],
            [(0, 6, "Brazil"), (15, 21, "carbon"), (22, 25, "tax")],
            id="disjoint",
        ),
        pytest.param(
            ["A <hi>carbon</hi> tax.", "A <hi>carbon</hi> <hi>tax</hi>."],
            [(2, 8, "carbon"), (9, 12, "tax")],
            id="same-span-once",
        ),
        pytest.param(
            ["<hi>nature-based</hi> fund", "<hi>nature</hi>-<hi>based</hi> fund"],
            [(0, 12, "nature-based")],
            id="overlapping-joined",
        ),
        pytest.param(["no tags", "no tags"], [], id="none"),
    ],
)
def test_merge_bolded_unions_spans(
    bolded_texts: list[str], expected_boldings: list[tuple[int, int, str]]
) -> None:
    """Spans from each bolded copy are unioned against the shared untagged text."""
    merged = merge_bolded(*bolded_texts)

    assert [
        (h.start_index, h.end_index, h.labelled_text) for h in merged.boldings
    ] == expected_boldings


def test_merge_bolded_raises_when_texts_differ() -> None:
    """Copies with different text would misalign spans, so it fails loudly."""
    with pytest.raises(ValueError):
        merge_bolded("a <hi>b</hi>", "a <hi>c</hi>")


def test_render_bolded_round_trips() -> None:
    text = "<hi>Brazil</hi> plans a <hi>carbon</hi> <hi>tax</hi>."
    assert render_bolded(merge_bolded(text)) == text


def test_from_vespa_passage_merges_exact_bolding() -> None:
    """A quoted query's phrase spans from `content_not_stemmed` are merged in."""
    vespa_passage = VespaPassage.model_validate(
        {
            "id": "tb-0",
            "content": "<hi>Brazil</hi> plans a carbon tax.",
            "content_not_stemmed": "Brazil plans a <hi>carbon</hi> <hi>tax</hi>.",
            "document_id": "doc-0",
        }
    )

    passage = Passage.from_vespa_passage(vespa_passage, bolding=True)

    assert passage.text == "Brazil plans a carbon tax."
    assert [h.labelled_text for h in passage.boldings] == ["Brazil", "carbon", "tax"]
