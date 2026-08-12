"""
Tests for the vendored `looks_like_*` passage heuristics.

Vendored from tests/test_passage_tables_of_contents.py,
tests/test_passage_reference_lists.py and tests/test_passage_prose_char_share.py
in the repo root, for the same reason `passages_derived_data` itself is - see
that module's docstring. Kept verbatim apart from calling the detectors with
`text` / `page_numbers` instead of a `Passage`, so the files stay diffable:
**change both, or neither**.

The examples are real (abbreviated) passages from CPR's Snowflake
`PRODUCTION.PUBLISHED.PASSAGES` table, chosen because each one drove a change to
the ruleset. They are kept here so that a future tweak that regresses one of them
fails loudly.
"""

import pytest
from passages_derived_data import (
    looks_like_reference_list,
    looks_like_short_heading,
    looks_like_table_of_contents,
    prose_char_share,
)

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
    assert looks_like_table_of_contents(TABLES_OF_CONTENTS[name], [])


@pytest.mark.parametrize("name", NOT_TABLES_OF_CONTENTS)
def test_ignores_other_short_line_blocks(name: str):
    assert not looks_like_table_of_contents(NOT_TABLES_OF_CONTENTS[name], [])


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
    assert not looks_like_table_of_contents(NUMBERED_LIST_OF_OBJECTIVES, [])


def test_page_veto_rejects_the_numbered_list_of_objectives():
    """What saves the above in practice: it is nowhere near the front matter."""
    assert not looks_like_table_of_contents(NUMBERED_LIST_OF_OBJECTIVES, [124])


class TestPageRule:
    """Front matter is at the front; a contents listing deep in a report is not one."""

    contents = TABLES_OF_CONTENTS["deep_hierarchical_numbering"]

    def test_front_matter_page_is_kept(self):
        assert looks_like_table_of_contents(self.contents, [3])

    def test_page_deep_in_the_document_is_vetoed(self):
        assert not looks_like_table_of_contents(self.contents, [150])

    def test_missing_page_data_leaves_the_text_signals_to_decide(self):
        assert looks_like_table_of_contents(self.contents, [])

    def test_earliest_page_is_the_one_that_counts(self):
        """A listing spanning a page boundary is judged by where it starts."""
        assert looks_like_table_of_contents(self.contents, [9, 10, 11])


REFERENCE_LISTS = {
    "author_year_colon_bibliography": (
        "Hansen, J., and L. Nazarenko, 2004: Soot climate forcing via snow and ice "
        "albedos. Proc. Natl. Acad. Sci., 101, 423-428, doi: "
        "10.1073/pnas.2237157100. Hansen, J., and Mki. Sato, 2004: Greenhouse gas "
        "growth rates. Proc. Natl. Acad. Sci., 101, 16109-16114, doi: "
        "10.1073/pnas.0406982101. Novakov, T., and J.E. Hansen, 2004: Black carbon "
        "emissions in the United Kingdom during the past four decades: An empirical "
        "analysis. Atmos. Environ., 38, 4155-4163."
    ),
    # 'www.' with no scheme, and the year in '(2024)' is not followed by
    # punctuation, so this scored far too low before.
    "numbered_endnotes_with_bare_urls": (
        '38 Greater London Authority (2024) "Operation Helios" to test London\'s '
        "response to extreme heat. www.london.gov.uk/operation-helios. (Accessed: 8 "
        "January 2026). 39 London Fire Brigade (2024) London Fire Brigade pilots new "
        "wildfire response vehicles. www.london-fire.gov.uk/news/2024-news/july. 40 "
        "Fearnley, C. and Kelman, I. (2021) Enhancing warnings. "
        "www.nationalpreparednesscommission.uk/publications/enhancing-warnings."
    ),
    # 'Accessed on' / 'Source:' footnote citations - the old locator list only knew
    # about 'Retrieved from' and 'Available online'.
    "source_footnotes_with_access_dates": (
        "7 2014 Dominica Street Lighting Tariff (71 cents per unit converted to US "
        'dollars). Source: DOMLEC. "DOMLEC Tariff Sheet effective as of September '
        '2007" http://www.domlec.dm/index.php/our-company/news/24-domlec-tariff-sheet. '
        "Accessed on 28 June 2015. 8 2014 St. Lucia Basic Energy Rate for Street "
        'Lighting converted to US Dollar. Source: LUCELEC "Basic Energy Rates" '
        "https://www.lucelec.com/content/energy-rates. Accessed on 28 June 2015."
    ),
    # No citation year, no doi, no URL. Carried by author initials (4.5 per 100
    # words) plus period density (22.4), which is the minimum of two signals.
    "numbered_technical_report_list": (
        "(1) M. Galbreath, Fire Endurance of Unit Masonry Walls. Technical Paper No. "
        "207, Division of Building Research, National Research Council Canada, Ottawa, "
        "October 1965. NRCC 8740. (2) M. Galbreath, Fire Endurance of Light Framed and "
        "Miscellaneous Assemblies. Technical Paper No. 222, Division of Building "
        "Research, National Research Council Canada, Ottawa, June 1966. NRCC 9085. (3) "
        "M. Galbreath, Fire Endurance of Concrete Assemblies. Technical Paper No. 235, "
        "Division of Building Research, National Research Council Canada, Ottawa, "
        "November 1966. NRCC 9279."
    ),
}

NOT_REFERENCE_LISTS = {
    # The case the heuristic exists to protect: assessment-report prose is dense in
    # parenthetical author-year citations and must be KEPT in search results.
    "ipcc_style_prose_with_parenthetical_cites": (
        "Women are significantly less likely than men to be in decent paid employment "
        "are, operating mainly as dependent family workers, working significantly "
        "longer hours than men when domestic work is taken into account, especially in "
        "rural areas (Abbott et al, 2015: 932). Female-headed households are more "
        "likely to be poor than male-headed households (and more likely to be "
        "extremely poor (EICV4) and to be food insecure (IMF, 2017: 35; WFP, 2015: 3). "
        "Female heads of household are often widows and tend to be less educated than "
        "their male counterparts (WFP, 2015: 3) are. A range of household situations "
        "can be problematic for women and children's food security, including "
        "female-headed households but also polygamous households, households with many "
        "children, and households with male breadwinners who fail to take "
        "responsibility for their families (Nzayisenga et al, 2016: 293-294)."
    ),
    # Dense in real author initials and periods, like a bibliography; the contact
    # details are what give it away.
    "attorney_signature_block": (
        "Respectfully submitted, Dated: January 29, 2021 By: /s/ Herbert J. Stern "
        "Florham Park, New Jersey Herbert J. Stern By: /s/ Paul J. Fishman STERN, "
        "KILCULLEN & RUFOLO, LLC Joel M. Silverstein jsilverstein@sgklaw.com 325 "
        "Columbia Turnpike, Suite 110 Florham Park, New Jersey 07932-0992 Telephone: "
        "973.535.1900 Facsimile: 973.535.9664 Theodore J. Boutrous, Jr., pro hac vice "
        "tboutrous@gibsondunn.com 333 South Grand Avenue Los Angeles, CA 90071"
    ),
    # Section numbering ('1.A.2.') used to be counted as author initials.
    "ghg_inventory_section_table": (
        "GREENHOUSE GAS SOURCE AND SINK CATEGORIES\n2000(1)\n(Gg)\nTotal National "
        "Emissions\n1. Energy\n1.A.1. Energy Industries\n1.A.2. Manufacturing "
        "Industries and Construction\n1.A.3. Transport\n1.A.4. Other Sectors\n1.B. "
        "Fugitive Emissions from Fuels\n2. Industrial Processes\n3. Solvent and Other "
        "Product Use\n4. Agriculture (3)\n5. Land-Use Change and Forestry\n6. Waste"
    ),
    # Numbered entries, periods and URLs, but it is a supplier directory.
    "supplier_contact_directory": (
        "Col. La Hacienda, Guadalupe, N.L. Mexico C.P. 67150 Telefonos: (81) "
        "8299-2222 FAX: Ext. 117 Sitio web: http://www.caba.com.mx/contactanos.html "
        "82. COMPONENTS Y EQUIPOS CABA S.A DE C.V. Saltillo-Monterrey Km. 12.65, "
        "Local 4C, Molinos del Rey Ramos Arizpe, Coah. Tel/Fax: (844) 490-2864 Sitio "
        "web: http://www.caba.com.mx/contactanos.html 83. FABRIEMPAQUES Y MAQUINARIA "
        "Av. Hacienda las Rosas No. 70-A Col. Hacienda Real de Tultepec Mexico Tel. / "
        "Fax: 01 (55) 2622 2072 E-mail: contacto@fabriempaques.com"
    ),
    # Prose that cites statutes by number - the corpus is mostly litigation and
    # legislation, so this must not be mistaken for a citation list.
    "prose_citing_statutes_by_number": (
        "Ghana's mitigation targets are supported by national legislation, including "
        "the Renewable Energy (Amendment) Act, 2020 (Act 1045), the Emissions Levy "
        "Act, 2023 (Act 1112), and the Fees and Charges (Miscellaneous Provisions) "
        "Act, 2022 (Act 1080), which provide a regulatory framework for emissions "
        "reduction and the promotion of low-carbon technologies. The NDC also "
        "underscores the importance of adaptation, framing it as an essential strategy "
        "for sustaining development under increasing climate stress."
    ),
    # Under the 20-word floor, so it is never judged. A real reference, and a
    # deliberate miss: without the floor the rule fires on short table rows and
    # page furniture.
    "short_passage": "Hansen, J., 2003: Can we defuse the global warming time bomb?",
}

# Footnotes 40-46 of a legal brief, interleaved with two sentences of the body text
# they annotate. Every one of the four signals lands just under its threshold - 0.8
# author initials, 1.6 citation years, 1.6 source locators, 15.6 periods per 100
# words - so none fires, and two are required. This is the known cost of dropping
# publication furniture ('ibid', 'supra', 'pp.') as a signal, which was cut because
# legal prose is full of it: a weighted sum can add five weak signals together and
# clear its bar, whereas a count of booleans cannot.
LEGAL_FOOTNOTES_WITH_NO_SINGLE_STRONG_SIGNAL = (
    "See, e.g., A. Ciavarella et al., Prolonged Siberian Heat of 2020 Almost "
    "Impossible Without Human Influence, CLIM. CHANGE (2021), "
    "https://link.springer.com/article/10.1007/s10584-021-03052-w. Human-induced "
    'climate change is already causing "widespread adverse impacts and related '
    'losses and damages" to people and ecosystems across the planet.44 40 41 WMO '
    "State of the Climate 2024, supra note 30. 42 Lijing Cheng, Record High "
    "Temperatures in the Ocean in 2024, 42 ADVANCES IN ATMOSPHERIC SCIENCES 1092 "
    "(2025). 43 Giguere et al., Climate Change and the Escalation of Global Extreme "
    "Heat: Assessing and Addressing the Risks, Climate Central, Red Cross, Crescent "
    "Climate Centre, World Weather Attribution (May 30, 2025), "
    "https://www.climatecentral.org/report/climate-change-and-the-escalation-of-"
    "global-extreme-heat-2025. 44 IPCC AR6 WGII at 9. 45 Id. 46 Id. processes, such "
    "as ocean acidification, sea level rise, and changes in average precipitation, "
    "are also having pervasive effects on human and natural systems."
)


@pytest.mark.xfail(
    reason="known blind spot: legal footnote blocks whose four citation signals all "
    "land just under threshold, so none fires and two are required",
    strict=True,
)
def test_legal_footnote_block_is_a_reference_list():
    assert looks_like_reference_list(LEGAL_FOOTNOTES_WITH_NO_SINGLE_STRONG_SIGNAL)


@pytest.mark.parametrize("text", REFERENCE_LISTS.values(), ids=REFERENCE_LISTS.keys())
def test_whether_reference_lists_are_detected(text):
    assert looks_like_reference_list(text)


@pytest.mark.parametrize(
    "text", NOT_REFERENCE_LISTS.values(), ids=NOT_REFERENCE_LISTS.keys()
)
def test_whether_non_reference_lists_are_not_detected(text):
    assert not looks_like_reference_list(text)


# `looks_like_short_heading` has no test file in the repo root to vendor, so these
# two are written here rather than copied.
def test_detects_short_allcaps_heading():
    assert looks_like_short_heading("TABLE 4: GHG EMISSIONS BY SECTOR")


def test_ignores_prose():
    assert not looks_like_short_heading(
        "The Party shall communicate a nationally determined contribution every five "
        "years, and each successive contribution shall represent a progression beyond "
        "the one it replaces."
    )


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
    assert prose_char_share(ACRONYM_GLOSSARY) == pytest.approx(0.0)


def test_prose_cell_table_scores_high():
    assert prose_char_share(PROSE_CELL_TABLE) > 0.9


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
    assert prose_char_share(HEADER_ROW_WITH_PROSE_CELLS) > 0.9


def test_single_long_line_scores_one():
    assert prose_char_share(SINGLE_LONG_LINE) == pytest.approx(1.0)


def test_single_short_line_scores_zero():
    assert prose_char_share(SINGLE_SHORT_LINE) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "\n\n", "  \n\t\n  "],
    ids=["empty", "spaces", "newlines", "mixed"],
)
def test_text_with_nothing_to_measure_scores_zero(text: str):
    """There is no share of nothing, and the division must not raise."""
    assert prose_char_share(text) == pytest.approx(0.0)
