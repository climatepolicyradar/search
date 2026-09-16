import pytest

from search.passage import Passage, _bolding_to_labels
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
    bolded = _bolding_to_labels(bolded_text)

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
