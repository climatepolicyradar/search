import pytest

from api.mcp.models import (
    ALTERNATIVE_NAMES_MAX,
    DESCRIPTION_MAX_CHARS,
    PASSAGE_TEXT_MAX_CHARS,
    DocumentDetail,
    DocumentHit,
    PassageHit,
    TopicHit,
)
from search.data_in_models import Document, Label, LabelRelationship
from search.label import LabelSearchResult
from search.passage import Passage


def label(relationship: str, label_type: str, value: str) -> LabelRelationship:
    return LabelRelationship(
        type=relationship,
        value=Label(id=f"{label_type}::{value}", type=label_type, value=value),
    )


def make_document(**overrides) -> Document:
    fields = {
        "id": "CCLW.document.1.0",
        "title": "Climate Change Act",
        "description": "An act about climate change.",
        "labels": [
            label("geography", "country", "Germany"),
            label("geography", "region", "Europe & Central Asia"),
            label("category", "category", "Law"),
        ],
        "attributes": {"published_date": "2023-10-23T00:00:00Z"},
    }
    return Document(**(fields | overrides))


def test_document_hit_keeps_what_the_model_needs():
    hit = DocumentHit.from_document(make_document())

    assert hit.id == "CCLW.document.1.0"
    assert hit.title == "Climate Change Act"
    assert hit.description == "An act about climate change."
    assert hit.geographies == ["Germany"]
    assert hit.regions == ["Europe & Central Asia"]
    assert hit.categories == ["Law"]
    assert hit.published_date == "2023-10-23T00:00:00Z"


def test_document_hit_drops_relationships_and_passages():
    assert set(DocumentHit.model_fields) == {
        "id",
        "title",
        "description",
        "geographies",
        "regions",
        "categories",
        "published_date",
    }


def test_long_description_is_shortened_with_an_ellipsis():
    hit = DocumentHit.from_document(make_document(description="word " * 200))

    assert hit.description is not None
    assert len(hit.description) <= DESCRIPTION_MAX_CHARS + 2
    assert hit.description.endswith("word …")


def test_description_at_the_limit_is_kept_whole():
    description = "x" * DESCRIPTION_MAX_CHARS

    assert (
        DocumentHit.from_document(make_document(description=description)).description
        == description
    )


def test_missing_description_stays_none():
    assert (
        DocumentHit.from_document(make_document(description=None)).description is None
    )


def test_missing_published_date_is_none():
    assert (
        DocumentHit.from_document(make_document(attributes={})).published_date is None
    )


def test_principal_is_flagged():
    document = make_document(labels=[label("status", "status", "Principal")])

    assert DocumentDetail.from_document(document).is_principal is True


def test_a_version_is_not_flagged_as_principal():
    assert DocumentDetail.from_document(make_document()).is_principal is False


def test_label_type_alone_does_not_count_as_a_geography():
    # `_label_values` reads the relationship type, as `api/download.py` does.
    document = make_document(labels=[label("related", "geography", "France")])

    assert DocumentHit.from_document(document).geographies == []


def test_passage_hit_keeps_what_the_model_needs():
    passage = Passage(
        text_block_id="p_1_b_2",
        document_id="CCLW.document.1.0",
        principal_id="CCLW.family.1.0",
        heading_text="Part 1",
        text="Flood insurance must be offered.",
        pages=[3],
        language="en",
    )

    hit = PassageHit.from_passage(passage, {"CCLW.family.1.0": "Climate Change Act"})

    assert hit == PassageHit(
        text_block_id="p_1_b_2",
        document_id="CCLW.document.1.0",
        principal_id="CCLW.family.1.0",
        document_title="Climate Change Act",
        heading="Part 1",
        text="Flood insurance must be offered.",
        text_truncated=False,
        pages=[3],
    )


def test_passage_without_a_principal_takes_its_own_documents_title():
    passage = Passage(document_id="UNFCCC.document.1.0", principal_id=None)

    hit = PassageHit.from_passage(passage, {"UNFCCC.document.1.0": "Kenya NDC"})

    assert hit.document_title == "Kenya NDC"


def test_passage_whose_document_was_not_found_has_no_title():
    assert PassageHit.from_passage(Passage(), {}).document_title is None


def test_long_passage_is_cut_and_flagged():
    passage = Passage(text="x" * (PASSAGE_TEXT_MAX_CHARS + 1))

    hit = PassageHit.from_passage(passage, {})

    # No sentence end or space to cut at, so it's a hard cut.
    assert hit.text == "x" * PASSAGE_TEXT_MAX_CHARS + " …"
    assert hit.text_truncated is True


def test_passage_entities_are_unescaped_but_angle_brackets_kept():
    passage = Passage(
        text="P&amp;G and R&amp;D, warming &lt; 1.5C, &quot;net zero&quot;",
        heading_text="Research &amp; development",
    )

    hit = PassageHit.from_passage(passage, {})

    assert hit.text == 'P&G and R&D, warming < 1.5C, "net zero"'
    assert hit.heading == "Research & development"


def test_entities_dont_count_towards_the_cut():
    # Unescaped first, so "&amp;" is one character when deciding whether to cut.
    passage = Passage(text="&amp;" * PASSAGE_TEXT_MAX_CHARS)

    hit = PassageHit.from_passage(passage, {})

    assert hit.text_truncated is False


def test_long_passage_is_cut_at_a_sentence_end():
    sentence = "The Committee must publish its advice. "
    passage = Passage(text=sentence * 100)

    hit = PassageHit.from_passage(passage, {})

    assert hit.text.endswith("advice. …")
    assert len(hit.text) <= PASSAGE_TEXT_MAX_CHARS + 2


def test_long_passage_is_cut_at_a_clause_break():
    # Legislation often has no full stops, just numbered clauses on new lines.
    clause = "(1) the Secretary of State must lay a report before Parliament\n"
    passage = Passage(text=clause * 50)

    hit = PassageHit.from_passage(passage, {})

    assert hit.text.endswith("before Parliament …")


def test_long_passage_without_sentence_ends_is_cut_at_a_space():
    passage = Passage(text="word " * 400)

    hit = PassageHit.from_passage(passage, {})

    assert hit.text.endswith("word …")
    assert "wor …" not in hit.text


def test_html_is_stripped_from_descriptions():
    hit = DocumentHit.from_document(
        make_document(description="<p>An act about<br>climate &amp; energy.</p>\n")
    )

    assert hit.description == "An act about climate & energy."


def test_topic_hit_caps_alternative_names():
    topic = LabelSearchResult(
        id="concept::Q1343",
        type="concept",
        value="adaptation finance",
        alternative_labels=[f"name {number}" for number in range(200)],
    )

    hit = TopicHit.from_label(topic)

    assert len(hit.alternative_names) == ALTERNATIVE_NAMES_MAX


def test_double_escaped_entities_are_unescaped():
    hit = DocumentHit.from_document(
        make_document(description="air quality.&amp;nbsp;It &amp;amp; more")
    )

    assert hit.description == "air quality. It & more"


def test_passage_hit_can_keep_the_full_text():
    long_text = "x" * (PASSAGE_TEXT_MAX_CHARS + 10)
    passage = Passage(text_block_id="d::1", document_id="d", text=long_text)

    hit = PassageHit.from_passage(passage, {}, max_chars=None)

    assert hit.text == long_text
    assert hit.text_truncated is False


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "Keep warming < 1.5C and emissions > 0 by 2050",
            "Keep warming < 1.5C and emissions > 0 by 2050",
        ),
        ("Targets &lt;2C&gt; apply", "Targets <2C> apply"),
    ],
    ids=["comparison-signs", "escaped-angle-brackets"],
)
def test_angle_brackets_in_prose_are_not_mistaken_for_tags(
    description: str, expected: str
):
    hit = DocumentHit.from_document(make_document(description=description))

    assert hit.description == expected


def test_double_escaped_tags_are_still_stripped():
    hit = DocumentHit.from_document(
        make_document(description="&amp;lt;p&amp;gt;An act&amp;lt;/p&amp;gt;")
    )

    assert hit.description == "An act"
