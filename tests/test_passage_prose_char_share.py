"""
Tests for the `prose_char_share` passage measure.

The shapes below are the ones that decided the measure's design: a glossary grid
it must score near zero, a prose-cell table it must score near one, and a table
with a short header row that character-weighting keeps and line-weighting throws
away.
"""

import pytest

from search.passage import Passage, prose_char_share

# A flattened acronym grid: every cell is a term or a short expansion, and the
# whole passage is what the measure exists to demote.
ACRONYM_GLOSSARY = (
    "ABBREVIATIONS AND ACRONYMS\n"
    "AFOLU\n"
    "Agriculture, Forestry and Other Land Use\n"
    "BAU\n"
    "Business As Usual\n"
    "CDM\n"
    "Clean Development Mechanism\n"
    "GHG\n"
    "Greenhouse Gas\n"
    "LULUCF\n"
    "Land Use, Land-Use Change and Forestry\n"
    "MRV\n"
    "Measurement, Reporting and Verification\n"
    "NDC\n"
    "Nationally Determined Contribution"
)

# A table whose cells are whole sentences - substantive content that happens to
# be laid out in a grid, and must NOT be demoted.
PROSE_CELL_TABLE = (
    "The Ministry of Environment shall prepare a national adaptation plan every five "
    "years, setting out the measures required to reduce vulnerability in the water sector.\n"
    "Coastal defence works shall be prioritised in the districts identified as most "
    "exposed to sea level rise, with funding drawn from the national climate resilience fund.\n"
    "Agricultural extension services shall promote drought-tolerant crop varieties and "
    "climate-smart practices among smallholder farmers in the arid and semi-arid lands."
)

# Three short column headings above three sentence-long body cells. Half the
# lines are short, so a line-weighted ratio scores this 0.50 and demotes a good
# table; almost all the characters are in the body, so the character-weighted
# share scores it 0.91 and keeps it.
HEADER_ROW_WITH_PROSE_CELLS = (
    "Sector\n"
    "Adaptation measure\n"
    "Responsible institution\n"
    "Water resources management shall be strengthened through catchment protection, "
    "rainwater harvesting and the rehabilitation of degraded wetlands across the basin.\n"
    "Coastal zones shall be protected by mangrove restoration and the enforcement of "
    "setback lines for all new development within two hundred metres of the shoreline.\n"
    "Public health systems shall expand surveillance of vector-borne disease and prepare "
    "contingency stocks of medicines ahead of each projected heatwave and flood season."
)

SINGLE_LONG_LINE = (
    "The Party shall communicate a nationally determined contribution every five years, "
    "and each successive contribution shall represent a progression beyond the one it replaces."
)

SINGLE_SHORT_LINE = "TABLE 4: GHG EMISSIONS BY SECTOR"


def test_acronym_glossary_scores_zero():
    """No cell in a glossary grid reaches 80 characters, so nothing counts."""
    assert prose_char_share(Passage(text=ACRONYM_GLOSSARY)) == pytest.approx(0.0)


def test_prose_cell_table_scores_high():
    assert prose_char_share(Passage(text=PROSE_CELL_TABLE)) > 0.9


def test_table_with_a_short_header_row_still_scores_high():
    """
    The case that decides character-weighting over line-weighting.

    Three short headings and three long body cells: counted by lines that is
    0.50, which sits below any threshold worth setting and would demote a
    perfectly good table. Counted by characters the headings are a rounding
    error and the passage scores 0.91.
    """
    lines = [
        line.strip() for line in HEADER_ROW_WITH_PROSE_CELLS.split("\n") if line.strip()
    ]
    line_weighted = sum(1 for line in lines if len(line) >= 80) / len(lines)

    assert line_weighted == pytest.approx(0.5)
    assert prose_char_share(Passage(text=HEADER_ROW_WITH_PROSE_CELLS)) > 0.9


def test_single_long_line_scores_one():
    assert prose_char_share(Passage(text=SINGLE_LONG_LINE)) == pytest.approx(1.0)


def test_single_short_line_scores_zero():
    assert prose_char_share(Passage(text=SINGLE_SHORT_LINE)) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "\n\n", "  \n\t\n  "],
    ids=["empty", "spaces", "newlines", "mixed"],
)
def test_text_with_nothing_to_measure_scores_zero(text: str):
    """There is no share of nothing, and the division must not raise."""
    assert prose_char_share(Passage(text=text)) == pytest.approx(0.0)
