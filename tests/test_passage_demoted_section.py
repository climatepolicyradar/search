"""
Tests for the `looks_like_demoted_section` passage heuristic.

The examples are real (abbreviated) headings from CPR's Snowflake
`PRODUCTION.PUBLISHED.PASSAGES`, drawn from the hand-labelled
`research/passage_type_detectors/data/demoted_section_validation_set.jsonl`. The
detector reads the section heading, so each case sets `type` and `heading_text`:

  - a body passage (`type="Text"`) is judged on its `heading_text` - the section it
    sits under - which is the gap this detector fills: `looks_like_reference_list`
    reads the passage's own text and sees no citation signal in ordinary prose;
  - a heading passage (`type` in sectionHeading / title / pageHeader) is judged on
    its own `text`, because `heading_id` on such a passage points at its PARENT, so
    `heading_text` here is the non-matching parent - the real corpus shape.

The length gate ships at 10 words and the self-heading types at
(sectionHeading, title, pageHeader); the two xfails below pin the known recall and
precision costs of those choices.
"""

import pytest

from search.passage import Passage, looks_like_demoted_section

DEMOTED_SECTIONS = {
    # Body prose under a References heading - looks_like_reference_list can't see it.
    "prose_under_references_heading": Passage(
        type="Text",
        heading_text="References",
        text="Boyd, R., ME Ibarraran. 2011. The cost of climate change in Mexico.",
    ),
    "prose_under_numbered_bibliography_heading": Passage(
        type="Text",
        heading_text="10.8 BIBLIOGRAPHIC REFERENCES",
        text="Understanding the health status of ecosystems is crucial for decisions.",
    ),
    "prose_under_authors_heading": Passage(
        type="Text",
        heading_text="Authors and Acknowledgments",
        text="Lea Kai. Climate Change Advisor. UNDP / Ministry of Environment.",
    ),
    # Heading passage judged on its OWN text; heading_text is the non-matching parent.
    "section_heading_self_references": Passage(
        type="sectionHeading",
        text="References",
        heading_text="Annex VI: Common reporting tables",
    ),
    # Widened _SELF_HEADING_TYPES: title / pageHeader headings judged on own text.
    "title_type_self_bibliography": Passage(
        type="title", text="BIBLIOGRAPHY", heading_text=""
    ),
    "page_header_self_references": Passage(
        type="pageHeader", text="REFERENCES", heading_text=""
    ),
    # max_words=10: title-type headings splice the document name onto the section
    # name and run long (7 words here) - missed at 6, caught at 10.
    "long_title_type_references": Passage(
        type="Text",
        heading_text="Austria's National Inventory Report 2024 - References",
        text="BRITISH GEOLOGICAL SURVEY (2006): World mineral production 2000-2004.",
    ),
    # Legal citation furniture.
    "list_of_authorities_and_references": Passage(
        type="Text",
        heading_text="ANNEX 1: LIST OF AUTHORITIES AND REFERENCES",
        text="I. African Union Authorities A. Treaties B. African Court.",
    ),
}

NOT_DEMOTED_SECTIONS = {
    # Plural-only: 'Terms of Reference' / 'Reference Scenario' are core NDC
    # vocabulary; the singular stem must not fire.
    "terms_of_reference": Passage(
        type="Text",
        heading_text="ANNEX 6: TERMS OF REFERENCE OF PROJECT MANAGEMENT UNIT STAFF",
        text="Terms of Reference of the National Project Coordinator.",
    ),
    "reference_scenario": Passage(
        type="sectionHeading",
        text="4.6.3.12 Reference Scenario",
        heading_text="4.6 Scenarios",
    ),
    # Caption / source-note veto: carries a keyword but is not a section.
    "source_note_caption": Passage(
        type="Text",
        heading_text="SOURCE: Prepared by the authors.",
        text="Based on the life cycle of the tourist destination.",
    ),
    "table_caption_with_references": Passage(
        type="Text",
        heading_text="Table 3-12 References and methodologies of carbon emission factors",
        text="Note: FEPC: Federation of Electric Power Companies of Japan.",
    ),
    # Substring the word boundaries reject: 'preferences' contains 'references'.
    "preferences_substring": Passage(
        type="Text",
        heading_text="CUSTOMER PREFERENCES.",
        text="Preferences and demands from consumers may change.",
    ),
    # A substantive section with no keyword at all.
    "substantive_heading": Passage(
        type="Text",
        heading_text="3 RENEWABLE ENERGY",
        text="The share of renewable energy in final consumption is shown in Figure 3.",
    ),
    # No heading -> nothing to judge on for a body passage.
    "no_heading": Passage(type="Text", heading_text=None, text="Some body text."),
}

# Known recall cost: a genuine bibliography heading longer than the 10-word gate.
# 'ANNEX III' numbering strips off, leaving ~17 words, so the gate misses it.
LONG_BIBLIOGRAPHY_HEADING = (
    "ANNEX III ANNOTATED BIBLIOGRAPHY OF NATIONAL-LEVEL ASSESSMENTS, REVIEWS AND "
    "DATABASES RELEVANT TO BIODIVERSITY STATUS AND MANAGEMENT PLANNING IN AFGHANISTAN"
)

# Known precision cost of max_words=10: sentence-shaped headings that carry a
# keyword and land within 10 words fire as false positives. Both are real
# substantive sections. At max_words=6 they were rejected; this is the trade.
SENTENCE_SHAPED_FALSE_POSITIVE = (
    "Authors' comments on the State party's observations on admissibility"
)


@pytest.mark.xfail(
    reason="known recall cost: reference/bibliography headings longer than the "
    "10-word gate are missed",
    strict=True,
)
def test_long_bibliography_heading_is_a_demoted_section():
    assert looks_like_demoted_section(
        Passage(type="Text", heading_text=LONG_BIBLIOGRAPHY_HEADING, text="Adil, A. 2001.")
    )


@pytest.mark.xfail(
    reason="known precision cost of max_words=10: sentence-shaped headings under 10 "
    "words that carry a keyword fire as false positives",
    strict=True,
)
def test_sentence_shaped_heading_is_not_a_demoted_section():
    assert not looks_like_demoted_section(
        Passage(type="Text", heading_text=SENTENCE_SHAPED_FALSE_POSITIVE, text="...")
    )


@pytest.mark.parametrize(
    "passage", DEMOTED_SECTIONS.values(), ids=DEMOTED_SECTIONS.keys()
)
def test_whether_demoted_sections_are_detected(passage):
    assert looks_like_demoted_section(passage)


@pytest.mark.parametrize(
    "passage", NOT_DEMOTED_SECTIONS.values(), ids=NOT_DEMOTED_SECTIONS.keys()
)
def test_whether_non_demoted_sections_are_not_detected(passage):
    assert not looks_like_demoted_section(passage)