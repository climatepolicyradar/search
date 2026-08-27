"""
A hardcoded list of values we would expect from the data-lake.

Due to some transformation issues we cannot rely on that data until those issues are resolved.
@see: https://linear.app/climate-policy-radar/issue/APP-2266/fusion-enrichment-fleshing-out-the-publishedcanonicallabels
"""

from search.data_in_models import (
    Label,
    LabelRelationship,
)

# region corporate disclosure
corporate_discloser = Label(
    type="category",
    id="category::Corporate Disclosure",
    value="Corporate Disclosure",
    labels=[],
)
corporate_voluntary_report = Label(
    id="entity_type::Corporate voluntary report",
    value="Corporate voluntary report",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=corporate_discloser,
        ),
    ],
)
corporate_voluntary_filing = Label(
    id="entity_type::Corporate voluntary filing",
    value="Corporate voluntary filing",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=corporate_discloser,
        ),
    ],
)

# region law
law = Label(type="category", id="category::Law", value="Law", labels=[])
framework_law = Label(
    id="law_type::Framework law",
    value="Framework law",
    type="law_type",
    labels=[LabelRelationship(type="subconcept_of", value=law)],
)

# region policy
policy = Label(type="category", id="category::Policy", value="Policy", labels=[])
mitigation = Label(
    id="topic::Mitigation",
    value="Mitigation",
    type="topic",
    labels=[
        LabelRelationship(type="subconcept_of", value=law),
        LabelRelationship(type="subconcept_of", value=policy),
    ],
)
adaptation = Label(
    id="topic::Adaptation",
    value="Adaptation",
    type="topic",
    labels=[
        LabelRelationship(type="subconcept_of", value=law),
        LabelRelationship(type="subconcept_of", value=policy),
    ],
)
loss_and_damage = Label(
    id="topic::Loss and damage",
    value="Loss and damage",
    type="topic",
    labels=[
        LabelRelationship(type="subconcept_of", value=law),
        LabelRelationship(type="subconcept_of", value=policy),
    ],
)
disaster_risk_management = Label(
    id="topic::Disaster risk management",
    value="Disaster risk management",
    type="topic",
    labels=[
        LabelRelationship(type="subconcept_of", value=law),
        LabelRelationship(type="subconcept_of", value=policy),
    ],
)

# region MCFs
multilateral_climate_fund_project = Label(
    type="category",
    id="category::Multilateral Climate Fund project",
    value="Multilateral Climate Fund project",
    labels=[],
)
adaptation_fund = Label(
    type="multilateral_climate_fund",
    id="agent::Adaptation Fund",
    value="Adaptation Fund",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project,
        )
    ],
)
the_climate_investment_funds = Label(
    type="multilateral_climate_fund",
    id="agent::The Climate Investment Funds",
    value="Climate Investment Funds",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project,
        )
    ],
)
green_climate_fund = Label(
    type="multilateral_climate_fund",
    id="agent::Green Climate Fund",
    value="Green Climate Fund",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project,
        )
    ],
)
global_environment_facility = Label(
    type="multilateral_climate_fund",
    id="agent::Global Environment Facility",
    value="Global Environment Facility",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project,
        )
    ],
)

multilateral_climate_fund_project_guidance = Label(
    id="entity_type::Guidance",
    value="Guidance",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project,
        )
    ],
)
multilateral_climate_fund_project_project = Label(
    id="entity_type::Project",
    value="Project",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project,
        )
    ],
)
concept_approved = Label(
    id="activity_status::Concept approved",
    value="Concept approved",
    type="activity_status",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project_project,
        )
    ],
)
project_approved = Label(
    id="activity_status::Project approved",
    value="Project approved",
    type="activity_status",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project_project,
        )
    ],
)
under_implementation = Label(
    id="activity_status::Under implementation",
    value="Under implementation",
    type="activity_status",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project_project,
        )
    ],
)
project_completed = Label(
    id="activity_status::Project completed",
    value="Project completed",
    type="activity_status",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project_project,
        )
    ],
)
cancelled = Label(
    id="activity_status::Cancelled",
    value="Cancelled",
    type="activity_status",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=multilateral_climate_fund_project_project,
        )
    ],
)

# region report
report = Label(type="category", id="category::Report", value="Report", labels=[])
climate_council_report = Label(
    id="report_type::Climate council report",
    value="Climate council report",
    type="report_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=report,
        )
    ],
)
annual_report = Label(
    id="entity_type::Annual report",
    value="Annual report",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=climate_council_report,
        ),
    ],
)
assessment_report = Label(
    id="entity_type::Assessment report",
    value="Assessment report",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=climate_council_report,
        )
    ],
)
industry_report = Label(
    id="report_type::Industry report",
    value="Industry report",
    type="report_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=report,
        )
    ],
)
offshore_wind_report = Label(
    id="entity_type::Offshore wind report",
    value="Offshore wind report",
    type="entity_type",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=industry_report,
        ),
    ],
)
individual = Label(
    id="author_type::Individual",
    value="Individual",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
academic_research = Label(
    id="author_type::Academic/Research",
    value="Academic/Research",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
national_body = Label(
    id="author_type::National body",
    value="National body",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
intergovernmental_organization = Label(
    id="author_type::Intergovernmental organization",
    value="Intergovernmental organization",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
corporate = Label(
    id="author_type::Corporate",
    value="Corporate",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
industry_body = Label(
    id="author_type::Industry body",
    value="Industry body",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
ngo_civil_society = Label(
    id="author_type::NGO/Civil society",
    value="NGO/Civil society",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)
other = Label(
    id="author_type::Other",
    value="Other",
    type="author_type",
    labels=[LabelRelationship(type="subconcept_of", value=report)],
)


# region un submission
un_submission = Label(
    type="category", id="category::UN submission", value="UN submission", labels=[]
)

unfccc = Label(
    id="un_convention::UNFCCC",
    value="UNFCCC",
    type="un_convention",
    labels=[LabelRelationship(type="subconcept_of", value=un_submission)],
)
nationally_determined_contribution = Label(
    id="entity_type::Nationally Determined Contribution (NDC)",
    value="Nationally Determined Contribution (NDC)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
national_adaptation_plan = Label(
    id="entity_type::National Adaptation Plan (NAP)",
    value="National Adaptation Plan (NAP)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
biennial_transparency_report = Label(
    id="entity_type::Biennial Transparency Report (BTR)",
    value="Biennial Transparency Report (BTR)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
long_term_low_emission_development_strategy = Label(
    id="entity_type::Long-term Low-emission Development Strategy (LT-LEDS)",
    value="Long-term Low-emission Development Strategy (LT-LEDS)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
biennial_update_report = Label(
    id="entity_type::Biennial Update Report (BUR)",
    value="Biennial Update Report (BUR)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
biennial_report = Label(
    id="entity_type::Biennial Report (BR)",
    value="Biennial Report (BR)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
national_communication = Label(
    id="entity_type::National Communication (NC)",
    value="National Communication (NC)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
national_inventory_report = Label(
    id="entity_type::National Inventory Report (NIR)",
    value="National Inventory Report (NIR)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)
adaptation_communication = Label(
    id="entity_type::Adaptation Communication (AC)",
    value="Adaptation Communication (AC)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unfccc)],
)

cbd = Label(
    id="un_convention::CBD",
    value="CBD",
    type="un_convention",
    labels=[LabelRelationship(type="subconcept_of", value=un_submission)],
)
national_biodiversity_strategy_and_action_plan = Label(
    id="entity_type::National Biodiversity Strategy and Action Plan (NBSAP)",
    value="National Biodiversity Strategy and Action Plan (NBSAP)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=cbd)],
)
national_report = Label(
    id="entity_type::National Report (NR)",
    value="National Report (NR)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=cbd)],
)
national_targets = Label(
    id="entity_type::National Targets (NT)",
    value="National Targets (NT)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=cbd)],
)

unccd = Label(
    id="un_convention::UNCCD",
    value="UNCCD",
    type="un_convention",
    labels=[LabelRelationship(type="subconcept_of", value=un_submission)],
)
voluntary_land_degradation_neutrality_targets = Label(
    id="entity_type::Voluntary Land Degradation Neutrality Targets (LDN-T)",
    value="Voluntary Land Degradation Neutrality Targets (LDN-T)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unccd)],
)
country_report = Label(
    id="entity_type::Country Report (CR)",
    value="Country Report (CR)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unccd)],
)
national_drought_plan = Label(
    id="entity_type::National Drought Plan (NDP)",
    value="National Drought Plan (NDP)",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=unccd)],
)

# region global stock take
global_stocktake_category_label = Label(
    id="category::Global Stocktake",
    value="Global Stocktake",
    type="category",
)

gst1_process_label = Label(
    id="process::GST1",
    value="GST1",
    type="process",
    labels=[
        LabelRelationship(
            type="subconcept_of",
            value=global_stocktake_category_label,
        )
    ],
)
party = Label(
    id="author_type::Party",
    value="Party",
    type="author_type",
    labels=[
        LabelRelationship(type="subconcept_of", value=global_stocktake_category_label)
    ],
)
nationally_determined_contribution.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
national_adaptation_plan.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
biennial_transparency_report.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
long_term_low_emission_development_strategy.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
biennial_update_report.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
biennial_report.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
national_communication.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
national_inventory_report.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
adaptation_communication.labels.append(
    LabelRelationship(
        type="subconcept_of",
        value=party,
    )
)
non_party = Label(
    id="author_type::Non-Party",
    value="Non-Party",
    type="author_type",
    labels=[
        LabelRelationship(type="subconcept_of", value=global_stocktake_category_label)
    ],
)
facilitative_sharing_of_views_report = Label(
    id="entity_type::Facilitative sharing of views report",
    value="Facilitative Sharing of Views Report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
fast_start_finance_report = Label(
    id="entity_type::Fast-Start Finance Report",
    value="Fast-Start Finance Report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
global_stocktake_synthesis_report = Label(
    id="entity_type::Global Stocktake Synthesis Report",
    value="Global Stocktake Synthesis Report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
intersessional_document = Label(
    id="entity_type::Intersessional Document",
    value="Intersessional Document",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
ipcc_report = Label(
    id="entity_type::IPCC Report",
    value="IPCC Report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
pre_session_document = Label(
    id="entity_type::Pre-Session Document",
    value="Pre-Session Document",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
publication = Label(
    id="entity_type::Publication",
    value="Publication",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
non_party_report = Label(
    id="entity_type::Report",
    value="Report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
submission_to_the_global_stocktake = Label(
    id="entity_type::Submission to the global stocktake",
    value="Submission to the global stocktake",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
summary_report = Label(
    id="entity_type::Summary report",
    value="Summary report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
synthesis_report = Label(
    id="entity_type::Synthesis report",
    value="Synthesis report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
technical_analysis_summary_report = Label(
    id="entity_type::technical analysis summary report",
    value="technical analysis summary report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)
technical_analysis_technical_report = Label(
    id="entity_type::technical analysis technical report",
    value="technical analysis technical report",
    type="entity_type",
    labels=[LabelRelationship(type="subconcept_of", value=non_party)],
)


labels_taxonomy = [
    corporate_discloser,
    corporate_voluntary_report,
    corporate_voluntary_filing,
    law,
    framework_law,
    policy,
    mitigation,
    adaptation,
    loss_and_damage,
    disaster_risk_management,
    multilateral_climate_fund_project,
    adaptation_fund,
    the_climate_investment_funds,
    green_climate_fund,
    global_environment_facility,
    multilateral_climate_fund_project_guidance,
    multilateral_climate_fund_project_project,
    concept_approved,
    project_approved,
    under_implementation,
    project_completed,
    cancelled,
    report,
    climate_council_report,
    annual_report,
    assessment_report,
    industry_report,
    offshore_wind_report,
    individual,
    academic_research,
    national_body,
    intergovernmental_organization,
    corporate,
    industry_body,
    ngo_civil_society,
    other,
    un_submission,
    party,
    non_party,
    unfccc,
    nationally_determined_contribution,
    national_adaptation_plan,
    biennial_transparency_report,
    long_term_low_emission_development_strategy,
    biennial_update_report,
    biennial_report,
    national_communication,
    national_inventory_report,
    adaptation_communication,
    cbd,
    national_biodiversity_strategy_and_action_plan,
    national_report,
    national_targets,
    unccd,
    voluntary_land_degradation_neutrality_targets,
    country_report,
    national_drought_plan,
    global_stocktake_category_label,
    gst1_process_label,
    facilitative_sharing_of_views_report,
    fast_start_finance_report,
    global_stocktake_synthesis_report,
    intersessional_document,
    ipcc_report,
    pre_session_document,
    publication,
    non_party_report,
    submission_to_the_global_stocktake,
    summary_report,
    synthesis_report,
    technical_analysis_summary_report,
    technical_analysis_technical_report,
]
