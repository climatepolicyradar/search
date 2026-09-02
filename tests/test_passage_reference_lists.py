"""
Tests for the `looks_like_reference_list` passage heuristic.

The examples below are real (abbreviated) passages from CPR's Snowflake
`PRODUCTION.PUBLISHED.PASSAGES` table, chosen because each one drove a change to
the ruleset. They are kept here so that a future tweak that regresses one of them
fails loudly.

Each entry is `(text, content_type)`. `content_type` matters below the density
floor - the bare-locator shortcut and the source-locator "strong signal" both
gate on it (`Text`/`footnote` only) - so a fixture that omits it would not be
exercising the same code path a real passage does.
"""

import pytest

from search.passage import Passage, looks_like_reference_list

REFERENCE_LISTS = {
    "author_year_colon_bibliography": (
        "Hansen, J., and L. Nazarenko, 2004: Soot climate forcing via snow and ice "
        "albedos. Proc. Natl. Acad. Sci., 101, 423-428, doi: "
        "10.1073/pnas.2237157100. Hansen, J., and Mki. Sato, 2004: Greenhouse gas "
        "growth rates. Proc. Natl. Acad. Sci., 101, 16109-16114, doi: "
        "10.1073/pnas.0406982101. Novakov, T., and J.E. Hansen, 2004: Black carbon "
        "emissions in the United Kingdom during the past four decades: An empirical "
        "analysis. Atmos. Environ., 38, 4155-4163.",
        "footnote",
    ),
    # 'www.' with no scheme, and the year in '(2024)' is not followed by
    # punctuation, so this scored far too low before.
    "numbered_endnotes_with_bare_urls": (
        '38 Greater London Authority (2024) "Operation Helios" to test London\'s '
        "response to extreme heat. www.london.gov.uk/operation-helios. (Accessed: 8 "
        "January 2026). 39 London Fire Brigade (2024) London Fire Brigade pilots new "
        "wildfire response vehicles. www.london-fire.gov.uk/news/2024-news/july. 40 "
        "Fearnley, C. and Kelman, I. (2021) Enhancing warnings. "
        "www.nationalpreparednesscommission.uk/publications/enhancing-warnings.",
        "footnote",
    ),
    # 'Accessed on' / 'Source:' footnote citations - the old locator list only knew
    # about 'Retrieved from' and 'Available online'.
    "source_footnotes_with_access_dates": (
        "7 2014 Dominica Street Lighting Tariff (71 cents per unit converted to US "
        'dollars). Source: DOMLEC. "DOMLEC Tariff Sheet effective as of September '
        '2007" http://www.domlec.dm/index.php/our-company/news/24-domlec-tariff-sheet. '
        "Accessed on 28 June 2015. 8 2014 St. Lucia Basic Energy Rate for Street "
        'Lighting converted to US Dollar. Source: LUCELEC "Basic Energy Rates" '
        "https://www.lucelec.com/content/energy-rates. Accessed on 28 June 2015.",
        "footnote",
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
        "November 1966. NRCC 9279.",
        "List",
    ),
    # A single reference item, not a list. Below the density floor, carried by author-initial + citation-year
    # only.
    "single_citation_below_density_floor": (
        "Hansen, J., 2003: Can we defuse the global warming time bomb?",
        "footnote",
    ),
    # Essentially just a locator - no author-initial, no citation-year at all - so
    # it can only ever be caught by the bare-locator shortcut, not the general
    # signal count.
    "bare_url_only_footnote": (
        "89 http://www.um.edu.mt/ceer.",
        "footnote",
    ),
    # Two strong signals (citation-year, source-locator), neither author-initial nor
    # period-density - the other half of the "two of four, at least one strong" rule
    # that `single_citation_below_density_floor` doesn't exercise.
    "institutional_citations_no_author_initial": (
        "90 EU-Commission (2006): Sixth annual report on the effectiveness of the "
        "strategy KOM (2006) {SEC(2006) 1078} "
        "http://eur-lex.europa.eu/LexUriServ/site/de/com/2006/com2006_0463de01.pdf "
        "91 EU-Commission (2005): Fifth annual report on the effectiveness of the "
        "strategy (SEC(2005) 826) http://eur-"
        "lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:52005DC0269:DE:HTML "
        "92 ACEA (2006): European Car Industry opposes recent statements of "
        "Environment Commissioner Stavros Dimas regarding CO2 Commitment. "
        "http://www.acea.be/files/Statement%20CO2%20-%20Dimas.pdf",
        "footnote",
    ),
    # Same two-strong-signals shape, but in body text rather than a footnote -
    # confirms the rule isn't accidentally footnote-specific.
    "org_citation_in_body_text": (
        "The Behavioural Insights Team (2023) How to build a Net Zero society. "
        "https://www.bi.team/wp-content/uploads/2023/01/How-to-build-a-Net-Zero-"
        "society_Jan-2023-1.pdf.",
        "Text",
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
        "responsibility for their families (Nzayisenga et al, 2016: 293-294).",
        "Text",
    ),
    # Dense in real author initials and periods, like a bibliography; the contact
    # details are what give it away.
    "attorney_signature_block": (
        "Respectfully submitted, Dated: January 29, 2021 By: /s/ Herbert J. Stern "
        "Florham Park, New Jersey Herbert J. Stern By: /s/ Paul J. Fishman STERN, "
        "KILCULLEN & RUFOLO, LLC Joel M. Silverstein jsilverstein@sgklaw.com 325 "
        "Columbia Turnpike, Suite 110 Florham Park, New Jersey 07932-0992 Telephone: "
        "973.535.1900 Facsimile: 973.535.9664 Theodore J. Boutrous, Jr., pro hac vice "
        "tboutrous@gibsondunn.com 333 South Grand Avenue Los Angeles, CA 90071",
        "Text",
    ),
    # Section numbering ('1.A.2.') used to be counted as author initials.
    "ghg_inventory_section_table": (
        "GREENHOUSE GAS SOURCE AND SINK CATEGORIES\n2000(1)\n(Gg)\nTotal National "
        "Emissions\n1. Energy\n1.A.1. Energy Industries\n1.A.2. Manufacturing "
        "Industries and Construction\n1.A.3. Transport\n1.A.4. Other Sectors\n1.B. "
        "Fugitive Emissions from Fuels\n2. Industrial Processes\n3. Solvent and Other "
        "Product Use\n4. Agriculture (3)\n5. Land-Use Change and Forestry\n6. Waste",
        "Table",
    ),
    # Numbered entries, periods and URLs, but it is a supplier directory.
    "supplier_contact_directory": (
        "Col. La Hacienda, Guadalupe, N.L. Mexico C.P. 67150 Telefonos: (81) "
        "8299-2222 FAX: Ext. 117 Sitio web: http://www.caba.com.mx/contactanos.html "
        "82. COMPONENTS Y EQUIPOS CABA S.A DE C.V. Saltillo-Monterrey Km. 12.65, "
        "Local 4C, Molinos del Rey Ramos Arizpe, Coah. Tel/Fax: (844) 490-2864 Sitio "
        "web: http://www.caba.com.mx/contactanos.html 83. FABRIEMPAQUES Y MAQUINARIA "
        "Av. Hacienda las Rosas No. 70-A Col. Hacienda Real de Tultepec Mexico Tel. / "
        "Fax: 01 (55) 2622 2072 E-mail: contacto@fabriempaques.com",
        "Text",
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
        "for sustaining development under increasing climate stress.",
        "Text",
    ),
    # A section heading, not a citation. Below the density floor, author-initial and
    # period-density alone used to be enough (two of any four signals); this is the
    # real example that showed that pair is not evidence of anything on its own -
    # it drove the move to requiring at least one of citation-year/source-locator.
    "section_heading_misread_as_citation": (
        "IV. DISCUSSION E. Article III Standing",
        "List",
    ),
    # A flattened map-legend row credited to its authors' initials - the other real
    # false positive from the same finding as `section_heading_misread_as_citation`.
    "flattened_map_legend_row": (
        "0.1 - 1.0 1.0 - 10.0 10.0 0 > Urban / Very Low 40 0\n"
        "G.I.S. Dr. B.S. Coulter & E.J. McDonald TEAGASC, JOHNSTOWN CASTLE 1998 N 40 "
        "80 Kilometers",
        "List",
    ),
    # A membership/registration-number signature block. Carries no '@' or 'Tel:' to
    # trip the contact-block veto, and - like the two cases above - only
    # author-initial and period-density, so it falls out of the same
    # at-least-one-strong-signal rule rather than needing its own veto.
    "membership_number_signature_block": (
        "No. 016750N For M. C. Bhandari & Co.     No. 001545C (Ram Babu) Partner M. "
        "No. 016151",
        "Table",
    ),
    # A document's own repeating CDN permalink in a page footer - textually
    # indistinguishable from a genuine bare-URL citation, which is why the
    # bare-locator shortcut is restricted to `Text`/`footnote` content types.
    "self_referential_permalink_in_footer": (
        "https://ort.cbd.int/national-reports/nr7/6399CD04-8246-9ACB-348E-854053CC049B",
        "pageFooter",
    ),
    # An electronic court-signature verification block, correctly typed as
    # `pageFooter` here - the content-type restriction on source-locator-as-a-
    # strong-signal catches it. Contrast with the known gap below, where the same
    # shape arrives typed as `footnote` instead.
    "e_signature_block_in_footer": (
        "Electronically signed by: JOSÉ JORGE RIBEIRO DA LUZ - 02/17/2022 10:24:40 AM "
        "http://pjesg.tjro.jus.br:80/consulta/Processo/ConsultaDocumento/listView.",
        "pageFooter",
    ),
}

# A known, accepted remaining gap: an e-signature verification block that happens to
# arrive typed as plain 'footnote' rather than 'pageFooter'. Content-type gating
# cannot distinguish it there, since 'footnote' is deliberately where genuine
# bare-URL citations live - fixing this would mean pattern-matching the signature
# phrasing itself, not anything content-type can tell apart.
E_SIGNATURE_BLOCK_TYPED_AS_FOOTNOTE = (
    "Electronically signed by: ANDREIA MACEDO BARRETO - 07/20/2023 18:40:38 "
    "https://pje.tjpa.jus.br/pje/Processo/ConsultaDocumento/listView.seam?x=23072018",
    "footnote",
)

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
    assert looks_like_reference_list(
        Passage(text=LEGAL_FOOTNOTES_WITH_NO_SINGLE_STRONG_SIGNAL, type="footnote")
    )


@pytest.mark.xfail(
    reason="known gap: e-signature blocks typed as 'footnote' rather than "
    "'pageFooter' can't be excluded by content-type gating alone",
    strict=True,
)
def test_e_signature_block_typed_as_footnote_is_not_a_reference_list():
    text, content_type = E_SIGNATURE_BLOCK_TYPED_AS_FOOTNOTE
    assert not looks_like_reference_list(Passage(text=text, type=content_type))


@pytest.mark.parametrize(
    "text,content_type", REFERENCE_LISTS.values(), ids=REFERENCE_LISTS.keys()
)
def test_whether_reference_lists_are_detected(text, content_type):
    assert looks_like_reference_list(Passage(text=text, type=content_type))


@pytest.mark.parametrize(
    "text,content_type", NOT_REFERENCE_LISTS.values(), ids=NOT_REFERENCE_LISTS.keys()
)
def test_whether_non_reference_lists_are_not_detected(text, content_type):
    assert not looks_like_reference_list(Passage(text=text, type=content_type))
