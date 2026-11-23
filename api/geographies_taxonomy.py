"""
A hardcoded region -> country -> subdivision hierarchy.

Regions and countries were generated from the Snowflake `published.labels`
```sql
select * from published.labels where type = 'country' or type = 'region';
```

Same rationale as labels_taxonomy.py: the equivalent relationships from the
data-lake is not available.

Subdivisions are every ISO 3166-2 subdivision of those countries, flat under the
country, as the geographies-api lists them.
"""

import re

import pycountry
from pycountry import SubdivisionHierarchy

from search.data_in_models import (
    Label,
    LabelRelationship,
)

region_EAS = Label(
    type="region",
    id="region::EAS",
    value="East Asia & Pacific",
    labels=[],
)

region_ECS = Label(
    type="region",
    id="region::ECS",
    value="Europe & Central Asia",
    labels=[],
)

region_LCN = Label(
    type="region",
    id="region::LCN",
    value="Latin America & Caribbean",
    labels=[],
)

region_MEA = Label(
    type="region",
    id="region::MEA",
    value="Middle East & North Africa",
    labels=[],
)

region_NAC = Label(
    type="region",
    id="region::NAC",
    value="North America",
    labels=[],
)

region_SAS = Label(
    type="region",
    id="region::SAS",
    value="South Asia",
    labels=[],
)

region_SSF = Label(
    type="region",
    id="region::SSF",
    value="Sub-Saharan Africa",
    labels=[],
)


def _country(code: str, name: str, region: Label) -> Label:
    return Label(
        type="country",
        id=f"country::{code}",
        value=name,
        labels=[LabelRelationship(type="subconcept_of", value=region)],
    )


regions = [
    region_EAS,
    region_ECS,
    region_LCN,
    region_MEA,
    region_NAC,
    region_SAS,
    region_SSF,
]

countries = [
    _country("AFG", "Afghanistan", region_MEA),
    _country("AGO", "Angola", region_SSF),
    _country("ALB", "Albania", region_ECS),
    _country("AND", "Andorra", region_ECS),
    _country("ARE", "United Arab Emirates", region_MEA),
    _country("ARG", "Argentina", region_LCN),
    _country("ARM", "Armenia", region_ECS),
    _country("ATG", "Antigua and Barbuda", region_LCN),
    _country("AUS", "Australia", region_EAS),
    _country("AUT", "Austria", region_ECS),
    _country("AZE", "Azerbaijan", region_ECS),
    _country("BDI", "Burundi", region_SSF),
    _country("BEL", "Belgium", region_ECS),
    _country("BEN", "Benin", region_SSF),
    _country("BFA", "Burkina Faso", region_SSF),
    _country("BGD", "Bangladesh", region_SAS),
    _country("BGR", "Bulgaria", region_ECS),
    _country("BHR", "Bahrain", region_MEA),
    _country("BHS", "Bahamas", region_LCN),
    _country("BIH", "Bosnia and Herzegovina", region_ECS),
    _country("BLR", "Belarus", region_ECS),
    _country("BLZ", "Belize", region_LCN),
    _country("BOL", "Bolivia", region_LCN),
    _country("BRA", "Brazil", region_LCN),
    _country("BRB", "Barbados", region_LCN),
    _country("BRN", "Brunei Darussalam", region_EAS),
    _country("BTN", "Bhutan", region_SAS),
    _country("BWA", "Botswana", region_SSF),
    _country("CAF", "Central African Republic", region_SSF),
    _country("CAN", "Canada", region_NAC),
    _country("CHE", "Switzerland", region_ECS),
    _country("CHL", "Chile", region_LCN),
    _country("CHN", "China", region_EAS),
    _country("CIV", "Côte d'Ivoire", region_SSF),
    _country("CMR", "Cameroon", region_SSF),
    _country("COD", "Congo, Democratic Republic of the", region_SSF),
    _country("COG", "Congo", region_SSF),
    _country("COK", "Cook Islands", region_EAS),
    _country("COL", "Colombia", region_LCN),
    _country("COM", "Comoros", region_SSF),
    _country("CPV", "Cabo Verde", region_SSF),
    _country("CRI", "Costa Rica", region_LCN),
    _country("CUB", "Cuba", region_LCN),
    _country("CYM", "Cayman Islands", region_LCN),
    _country("CYP", "Cyprus", region_ECS),
    _country("CZE", "Czechia", region_ECS),
    _country("DEU", "Germany", region_ECS),
    _country("DJI", "Djibouti", region_MEA),
    _country("DMA", "Dominica", region_LCN),
    _country("DNK", "Denmark", region_ECS),
    _country("DOM", "Dominican Republic", region_LCN),
    _country("DZA", "Algeria", region_MEA),
    _country("ECU", "Ecuador", region_LCN),
    _country("EGY", "Egypt", region_MEA),
    _country("ERI", "Eritrea", region_SSF),
    _country("ESP", "Spain", region_ECS),
    _country("EST", "Estonia", region_ECS),
    _country("ETH", "Ethiopia", region_SSF),
    _country("EUR", "European Union", region_ECS),
    _country("FIN", "Finland", region_ECS),
    _country("FJI", "Fiji", region_EAS),
    _country("FRA", "France", region_ECS),
    _country("FSM", "Micronesia", region_EAS),
    _country("GAB", "Gabon", region_SSF),
    _country("GBR", "United Kingdom", region_ECS),
    _country("GEO", "Georgia", region_ECS),
    _country("GHA", "Ghana", region_SSF),
    _country("GIN", "Guinea", region_SSF),
    _country("GMB", "Gambia", region_SSF),
    _country("GNB", "Guinea-Bissau", region_SSF),
    _country("GNQ", "Equatorial Guinea", region_SSF),
    _country("GRC", "Greece", region_ECS),
    _country("GRD", "Grenada", region_LCN),
    _country("GRL", "Greenland", region_ECS),
    _country("GTM", "Guatemala", region_LCN),
    _country("GUY", "Guyana", region_LCN),
    _country("HKG", "Hong Kong", region_EAS),
    _country("HND", "Honduras", region_LCN),
    _country("HRV", "Croatia", region_ECS),
    _country("HTI", "Haiti", region_LCN),
    _country("HUN", "Hungary", region_ECS),
    _country("IDN", "Indonesia", region_EAS),
    _country("IMN", "Isle of Man", region_ECS),
    _country("IND", "India", region_SAS),
    _country("IRL", "Ireland", region_ECS),
    _country("IRN", "Iran", region_MEA),
    _country("IRQ", "Iraq", region_MEA),
    _country("ISL", "Iceland", region_ECS),
    _country("ISR", "Israel", region_MEA),
    _country("ITA", "Italy", region_ECS),
    _country("JAM", "Jamaica", region_LCN),
    _country("JOR", "Jordan", region_MEA),
    _country("JPN", "Japan", region_EAS),
    _country("KAZ", "Kazakhstan", region_ECS),
    _country("KEN", "Kenya", region_SSF),
    _country("KGZ", "Kyrgyzstan", region_ECS),
    _country("KHM", "Cambodia", region_EAS),
    _country("KIR", "Kiribati", region_EAS),
    _country("KNA", "Saint Kitts and Nevis", region_LCN),
    _country("KOR", "South Korea", region_EAS),
    _country("KWT", "Kuwait", region_MEA),
    _country("LAO", "Laos", region_EAS),
    _country("LBN", "Lebanon", region_MEA),
    _country("LBR", "Liberia", region_SSF),
    _country("LBY", "Libya", region_MEA),
    _country("LCA", "Saint Lucia", region_LCN),
    _country("LIE", "Liechtenstein", region_ECS),
    _country("LKA", "Sri Lanka", region_SAS),
    _country("LSO", "Lesotho", region_SSF),
    _country("LTU", "Lithuania", region_ECS),
    _country("LUX", "Luxembourg", region_ECS),
    _country("LVA", "Latvia", region_ECS),
    _country("MAR", "Morocco", region_MEA),
    _country("MCO", "Monaco", region_ECS),
    _country("MDA", "Moldova", region_ECS),
    _country("MDG", "Madagascar", region_SSF),
    _country("MDV", "Maldives", region_SAS),
    _country("MEX", "Mexico", region_LCN),
    _country("MHL", "Marshall Islands", region_EAS),
    _country("MKD", "North Macedonia", region_ECS),
    _country("MLI", "Mali", region_SSF),
    _country("MLT", "Malta", region_MEA),
    _country("MMR", "Myanmar", region_EAS),
    _country("MNE", "Montenegro", region_ECS),
    _country("MNG", "Mongolia", region_EAS),
    _country("MOZ", "Mozambique", region_SSF),
    _country("MRT", "Mauritania", region_SSF),
    _country("MUS", "Mauritius", region_SSF),
    _country("MWI", "Malawi", region_SSF),
    _country("MYS", "Malaysia", region_EAS),
    _country("NAM", "Namibia", region_SSF),
    _country("NER", "Niger", region_SSF),
    _country("NGA", "Nigeria", region_SSF),
    _country("NIC", "Nicaragua", region_LCN),
    _country("NIU", "Niue", region_EAS),
    _country("NLD", "Netherlands", region_ECS),
    _country("NOR", "Norway", region_ECS),
    _country("NPL", "Nepal", region_SAS),
    _country("NRU", "Nauru", region_EAS),
    _country("NZL", "New Zealand", region_EAS),
    _country("OMN", "Oman", region_MEA),
    _country("PAK", "Pakistan", region_MEA),
    _country("PAN", "Panama", region_LCN),
    _country("PER", "Peru", region_LCN),
    _country("PHL", "Philippines", region_EAS),
    _country("PLW", "Palau", region_EAS),
    _country("PNG", "Papua New Guinea", region_EAS),
    _country("POL", "Poland", region_ECS),
    _country("PRK", "North Korea", region_EAS),
    _country("PRT", "Portugal", region_ECS),
    _country("PRY", "Paraguay", region_LCN),
    _country("PSE", "Palestine, State of", region_MEA),
    _country("QAT", "Qatar", region_MEA),
    _country("ROU", "Romania", region_ECS),
    _country("RUS", "Russian Federation", region_ECS),
    _country("RWA", "Rwanda", region_SSF),
    _country("SAU", "Saudi Arabia", region_MEA),
    _country("SDN", "Sudan", region_SSF),
    _country("SEN", "Senegal", region_SSF),
    _country("SGP", "Singapore", region_EAS),
    _country("SLB", "Solomon Islands", region_EAS),
    _country("SLE", "Sierra Leone", region_SSF),
    _country("SLV", "El Salvador", region_LCN),
    _country("SMR", "San Marino", region_ECS),
    _country("SOM", "Somalia", region_SSF),
    _country("SRB", "Serbia", region_ECS),
    _country("SSD", "South Sudan", region_SSF),
    _country("STP", "Sao Tome and Principe", region_SSF),
    _country("SUR", "Suriname", region_LCN),
    _country("SVK", "Slovakia", region_ECS),
    _country("SVN", "Slovenia", region_ECS),
    _country("SWE", "Sweden", region_ECS),
    _country("SWZ", "Eswatini", region_SSF),
    _country("SYC", "Seychelles", region_SSF),
    _country("SYR", "Syria", region_MEA),
    _country("TCD", "Chad", region_SSF),
    _country("TGO", "Togo", region_SSF),
    _country("THA", "Thailand", region_EAS),
    _country("TJK", "Tajikistan", region_ECS),
    _country("TKM", "Turkmenistan", region_ECS),
    _country("TLS", "Timor-Leste", region_EAS),
    _country("TON", "Tonga", region_EAS),
    _country("TTO", "Trinidad and Tobago", region_LCN),
    _country("TUN", "Tunisia", region_MEA),
    _country("TUR", "Türkiye", region_ECS),
    _country("TUV", "Tuvalu", region_EAS),
    _country("TWN", "Taiwan", region_EAS),
    _country("TZA", "Tanzania", region_SSF),
    _country("UGA", "Uganda", region_SSF),
    _country("UKR", "Ukraine", region_ECS),
    _country("URY", "Uruguay", region_LCN),
    _country("USA", "United States of America", region_NAC),
    _country("UZB", "Uzbekistan", region_ECS),
    _country("VAT", "Holy See (Vatican City State)", region_ECS),
    _country("VCT", "Saint Vincent and the Grenadines", region_LCN),
    _country("VEN", "Venezuela, Bolivarian Republic of", region_LCN),
    _country("VNM", "Viet Nam", region_EAS),
    _country("VUT", "Vanuatu", region_EAS),
    _country("WSM", "Samoa", region_EAS),
    Label(
        type="country",
        id="country::XAB",
        value="International",
        labels=[],
    ),
    _country("YEM", "Yemen", region_MEA),
    _country("ZAF", "South Africa", region_SSF),
    _country("ZMB", "Zambia", region_SSF),
    _country("ZWE", "Zimbabwe", region_SSF),
    # Not in the Snowflake table; comes from the admin service (CCLW/CPR national
    # law documents, e.g. CCLW.family.i00000218.n0000, CPR.family.i00002239.n0000).
    _country("XKX", "Kosovo", region_ECS),
]

SUBDIVISION_NAMES = {
    "ID-KU": "North Kalimantan",
    "IN-AR": "Arunachal Pradesh",
    "IN-BR": "Bihar",
    "IN-CH": "Chandigarh",
    "IN-GJ": "Gujarat",
    "IN-HP": "Himachal Pradesh",
    "IN-HR": "Haryana",
    "IN-JH": "Jharkhand",
    "IN-JK": "Jammu and Kashmir",
    "IN-MH": "Maharashtra",
    "IN-ML": "Meghalaya",
    "IN-NL": "Nagaland",
    "IN-RJ": "Rajasthan",
    "IN-TS": "Telangana",
    "IN-TN": "Tamil Nadu",
    "IN-UK": "Uttarakhand",
    "MX-CMX": "Mexico City",
    "PT-20": "Azores",
}


def subdivision_label(subdivision: SubdivisionHierarchy, country: Label) -> Label:
    return Label(
        value=SUBDIVISION_NAMES.get(subdivision.code, re.sub(r"\s*\[.*\]$", "", subdivision.name)),
        labels=[LabelRelationship(type="subconcept_of", value=country)],
        id=f"subdivision::{subdivision.code}",
        type="subdivision",
    )


def country_id(subdivision: SubdivisionHierarchy) -> str:
    return f"country::{pycountry.countries.lookup(subdivision.country_code).alpha_3}"


countries_by_id = {country.id: country for country in countries}

subdivisions = [
    subdivision_label(
        subdivision=subdivision,
        country=countries_by_id[country_id(subdivision)],
    )
    for subdivision in pycountry.subdivisions
    if country_id(subdivision) in countries_by_id
]

geographies_taxonomy = [*regions, *countries, *subdivisions]
