"""Tests for the `looks_like_table_of_contents` passage heuristic."""


import pytest

from search.passage import Passage, looks_like_table_of_contents

TABLES_OF_CONTENTS = {
    "contents_fragment_with_page_numbers": (
        "7.1.1 Resources 40\n"
        "7.1.2 Transformation 41\n"
        "7.1.3 Demand 41\n"
        "7.2 Transport. 41\n"
        "7.3 Trade and Tourism 42 2"
    ),
    "roman_folios_and_dot_leader_stubs": (
        "List of acronyms\n"
        "i\n"
        "List of figures.\n"
        "ii\n"
        "1 Introduction.\n"
        "2 National Biodiversity Strategy\n"
        "Vision 2050.\n"
        "Mission 2030\n"
        "national objectives\n"
        "Principles governing the strategy\n"
        "3 National Action Plans 2026-2030 for Biodiversity\n"
        "4. Implementation Conditions"
    ),
    "deep_hierarchical_numbering": (
        "1. Acknowledgement 6\n"
        "2. About the Guideline 7\n"
        "2.1. Purpose of the Guideline 7\n"
        "2.2. Scope of the Guideline 8\n"
        "2.2.1. Applicability 8\n"
        "2.2.2. Exemption 9\n"
        "2.2.3. Precedence 9\n"
        "2.2.4. Reference Standards and green building rating programmes 10"
    ),
    "section_numbering_without_locators": (
        "influence energy system and greenhouse gas emissions\n"
        "4.2. Dimension Decarbonisation\n"
        "4.2.1. GHG emissions and removals\n"
        "4.2.2. Renewable energy\n"
        "4.3. Energy Efficiency Dimension"
    ),
}

NOT_TABLES_OF_CONTENTS = {
    "tonnage_table": "Bokoro\n600* tons\nAm Djarass\n1,000* tonnes\nTOTAL\n28,450 tonnes",
    "consultancy_footer_with_stray_page_number": (
        "MMIC\nIES ...\nMYANMAR\n748\nIntelligent Energy Systems\nINTERNATIONAL CONSULTANTS"
    ),
    "form_status_fields": (
        "Status *\nImplementation Progress *\nActivity started - progress on track\n20 %"
    ),
    "repeated_row_label_with_trailing_numbers": (
        "Vehicle Emissions Category\n"
        "10-minute soak NMOG+NOx (g/mi)\n"
        "40-minute soak NMOG+NOx (g/mi)\n"
        "Bin 70\n"
        "Bin 65\n"
        "Bin 60\n"
        "Bin 55\n"
        "Bin 50\n"
        "Bin 45"
    ),
    "chart_data_labels": (
        "Mid-Term\n16.00\n14.00\n12.00\n10.00\n"
        "9.00 BESS: 5472 MWH Zero Routine Flaring by 2030\n"
        "8.00\n6.00\n4.00\n2.00\n0.00"
    ),
}


@pytest.mark.parametrize("name", TABLES_OF_CONTENTS)
def test_detects_tables_of_contents(name: str):
    assert looks_like_table_of_contents(Passage(text=TABLES_OF_CONTENTS[name]))


@pytest.mark.parametrize("name", NOT_TABLES_OF_CONTENTS)
def test_ignores_other_short_line_blocks(name: str):
    assert not looks_like_table_of_contents(Passage(text=NOT_TABLES_OF_CONTENTS[name]))


# A short numbered list of objectives from a national adaptation plan. The text
# features cannot tell it apart from a contents listing – this is why page number is 
# used as a feature.
NUMBERED_LIST_OF_OBJECTIVES = (
    "1. Guarantee the quality of drinking water for human consumption\n"
    "2. Improve liquid and solid sanitation\n"
    "3. Improve the system for preventing vector-borne disease\n"
    "4. Increase production autonomy in the face of hydrological cycles\n"
    "5. Increase the profitability of agroforestry"
)


@pytest.mark.xfail(
    reason="known false-positive class: the text signals alone cannot separate a "
    "numbered list of objectives from a numbered contents listing",
    strict=True,
)
def test_numbered_list_of_objectives_is_not_a_contents_listing():
    assert not looks_like_table_of_contents(Passage(text=NUMBERED_LIST_OF_OBJECTIVES))


def test_page_veto_rejects_the_numbered_list_of_objectives():
    """What saves the above in practice: it is nowhere near the front matter."""
    assert not looks_like_table_of_contents(
        Passage(text=NUMBERED_LIST_OF_OBJECTIVES, pages=[124])
    )


class TestPageRule:
    """Front matter is at the front; a contents listing deep in a report is not one."""

    contents = TABLES_OF_CONTENTS["deep_hierarchical_numbering"]

    def test_front_matter_page_is_kept(self):
        assert looks_like_table_of_contents(Passage(text=self.contents, pages=[3]))

    def test_page_deep_in_the_document_is_vetoed(self):
        assert not looks_like_table_of_contents(
            Passage(text=self.contents, pages=[150])
        )

    def test_missing_page_data_leaves_the_text_signals_to_decide(self):
        assert looks_like_table_of_contents(Passage(text=self.contents, pages=[]))

    def test_earliest_page_is_the_one_that_counts(self):
        """A listing spanning a page boundary is judged by where it starts."""
        assert looks_like_table_of_contents(
            Passage(text=self.contents, pages=[9, 10, 11])
        )
