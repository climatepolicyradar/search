"""
A hardcoded region -> country -> subdivision hierarchy.

Generated from the Snoflake `published.labels`
```sql
select * from published.labels where
    type = 'subdivision'
    or type = 'country'
    or type = 'region';
```

Same rationale as labels_taxonomy.py: the equivalent relationships from the
data-lake is not available.

Claude used to build the relationships.
"""

from search.data_in_models import (
    Label,
    LabelRelationship,
)

# region regions
region_EAS = Label(
    type="region", id="region::EAS", value="East Asia & Pacific", labels=[]
)
region_ECS = Label(
    type="region", id="region::ECS", value="Europe & Central Asia", labels=[]
)
region_LCN = Label(
    type="region", id="region::LCN", value="Latin America & Caribbean", labels=[]
)
region_MEA = Label(
    type="region", id="region::MEA", value="Middle East & North Africa", labels=[]
)
region_NAC = Label(type="region", id="region::NAC", value="North America", labels=[])
region_SAS = Label(type="region", id="region::SAS", value="South Asia", labels=[])
region_SSF = Label(
    type="region", id="region::SSF", value="Sub-Saharan Africa", labels=[]
)

# region countries
country_AFG = Label(
    type="country",
    id="country::AFG",
    value="Afghanistan",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_AGO = Label(
    type="country",
    id="country::AGO",
    value="Angola",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_ALB = Label(
    type="country",
    id="country::ALB",
    value="Albania",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_AND = Label(
    type="country",
    id="country::AND",
    value="Andorra",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_ARE = Label(
    type="country",
    id="country::ARE",
    value="United Arab Emirates",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ARG = Label(
    type="country",
    id="country::ARG",
    value="Argentina",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_ARM = Label(
    type="country",
    id="country::ARM",
    value="Armenia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_ATG = Label(
    type="country",
    id="country::ATG",
    value="Antigua and Barbuda",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_AUS = Label(
    type="country",
    id="country::AUS",
    value="Australia",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_AUT = Label(
    type="country",
    id="country::AUT",
    value="Austria",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_AZE = Label(
    type="country",
    id="country::AZE",
    value="Azerbaijan",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_BDI = Label(
    type="country",
    id="country::BDI",
    value="Burundi",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_BEL = Label(
    type="country",
    id="country::BEL",
    value="Belgium",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_BEN = Label(
    type="country",
    id="country::BEN",
    value="Benin",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_BFA = Label(
    type="country",
    id="country::BFA",
    value="Burkina Faso",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_BGD = Label(
    type="country",
    id="country::BGD",
    value="Bangladesh",
    labels=[LabelRelationship(type="subconcept_of", value=region_SAS)],
)
country_BGR = Label(
    type="country",
    id="country::BGR",
    value="Bulgaria",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_BHR = Label(
    type="country",
    id="country::BHR",
    value="Bahrain",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_BHS = Label(
    type="country",
    id="country::BHS",
    value="Bahamas",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_BIH = Label(
    type="country",
    id="country::BIH",
    value="Bosnia and Herzegovina",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_BLR = Label(
    type="country",
    id="country::BLR",
    value="Belarus",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_BLZ = Label(
    type="country",
    id="country::BLZ",
    value="Belize",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_BOL = Label(
    type="country",
    id="country::BOL",
    value="Bolivia",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_BRA = Label(
    type="country",
    id="country::BRA",
    value="Brazil",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_BRB = Label(
    type="country",
    id="country::BRB",
    value="Barbados",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_BRN = Label(
    type="country",
    id="country::BRN",
    value="Brunei Darussalam",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_BTN = Label(
    type="country",
    id="country::BTN",
    value="Bhutan",
    labels=[LabelRelationship(type="subconcept_of", value=region_SAS)],
)
country_BWA = Label(
    type="country",
    id="country::BWA",
    value="Botswana",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_CAF = Label(
    type="country",
    id="country::CAF",
    value="Central African Republic",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_CAN = Label(
    type="country",
    id="country::CAN",
    value="Canada",
    labels=[LabelRelationship(type="subconcept_of", value=region_NAC)],
)
country_CHE = Label(
    type="country",
    id="country::CHE",
    value="Switzerland",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_CHL = Label(
    type="country",
    id="country::CHL",
    value="Chile",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_CHN = Label(
    type="country",
    id="country::CHN",
    value="China",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_CIV = Label(
    type="country",
    id="country::CIV",
    value="Côte d'Ivoire",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_CMR = Label(
    type="country",
    id="country::CMR",
    value="Cameroon",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_COD = Label(
    type="country",
    id="country::COD",
    value="Congo",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_COG = Label(
    type="country",
    id="country::COG",
    value="Congo",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_COK = Label(
    type="country",
    id="country::COK",
    value="Cook Islands",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_COL = Label(
    type="country",
    id="country::COL",
    value="Colombia",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_COM = Label(
    type="country",
    id="country::COM",
    value="Comoros",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_CPV = Label(
    type="country",
    id="country::CPV",
    value="Cabo Verde",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_CRI = Label(
    type="country",
    id="country::CRI",
    value="Costa Rica",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_CUB = Label(
    type="country",
    id="country::CUB",
    value="Cuba",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_CYM = Label(
    type="country",
    id="country::CYM",
    value="Cayman Islands",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_CYP = Label(
    type="country",
    id="country::CYP",
    value="Cyprus",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_CZE = Label(
    type="country",
    id="country::CZE",
    value="Czechia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_DEU = Label(
    type="country",
    id="country::DEU",
    value="Germany",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_DJI = Label(
    type="country",
    id="country::DJI",
    value="Djibouti",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_DMA = Label(
    type="country",
    id="country::DMA",
    value="Dominica",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_DNK = Label(
    type="country",
    id="country::DNK",
    value="Denmark",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_DOM = Label(
    type="country",
    id="country::DOM",
    value="Dominican Republic",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_DZA = Label(
    type="country",
    id="country::DZA",
    value="Algeria",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ECU = Label(
    type="country",
    id="country::ECU",
    value="Ecuador",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_EGY = Label(
    type="country",
    id="country::EGY",
    value="Egypt",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ERI = Label(
    type="country",
    id="country::ERI",
    value="Eritrea",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_ESP = Label(
    type="country",
    id="country::ESP",
    value="Spain",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_EST = Label(
    type="country",
    id="country::EST",
    value="Estonia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_ETH = Label(
    type="country",
    id="country::ETH",
    value="Ethiopia",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_EUR = Label(
    type="country",
    id="country::EUR",
    value="European Union",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_FIN = Label(
    type="country",
    id="country::FIN",
    value="Finland",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_FJI = Label(
    type="country",
    id="country::FJI",
    value="Fiji",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_FRA = Label(
    type="country",
    id="country::FRA",
    value="France",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_FSM = Label(
    type="country",
    id="country::FSM",
    value="Micronesia",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_GAB = Label(
    type="country",
    id="country::GAB",
    value="Gabon",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_GBR = Label(
    type="country",
    id="country::GBR",
    value="United Kingdom",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_GEO = Label(
    type="country",
    id="country::GEO",
    value="Georgia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_GHA = Label(
    type="country",
    id="country::GHA",
    value="Ghana",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_GIN = Label(
    type="country",
    id="country::GIN",
    value="Guinea",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_GMB = Label(
    type="country",
    id="country::GMB",
    value="Gambia",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_GNB = Label(
    type="country",
    id="country::GNB",
    value="Guinea-Bissau",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_GNQ = Label(
    type="country",
    id="country::GNQ",
    value="Equatorial Guinea",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_GRC = Label(
    type="country",
    id="country::GRC",
    value="Greece",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_GRD = Label(
    type="country",
    id="country::GRD",
    value="Grenada",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_GRL = Label(
    type="country",
    id="country::GRL",
    value="Greenland",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_GTM = Label(
    type="country",
    id="country::GTM",
    value="Guatemala",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_GUY = Label(
    type="country",
    id="country::GUY",
    value="Guyana",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_HKG = Label(
    type="country",
    id="country::HKG",
    value="Hong Kong",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_HND = Label(
    type="country",
    id="country::HND",
    value="Honduras",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_HRV = Label(
    type="country",
    id="country::HRV",
    value="Croatia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_HTI = Label(
    type="country",
    id="country::HTI",
    value="Haiti",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_HUN = Label(
    type="country",
    id="country::HUN",
    value="Hungary",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_IDN = Label(
    type="country",
    id="country::IDN",
    value="Indonesia",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_IMN = Label(
    type="country",
    id="country::IMN",
    value="Isle of Man",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_IND = Label(
    type="country",
    id="country::IND",
    value="India",
    labels=[LabelRelationship(type="subconcept_of", value=region_SAS)],
)
country_IRL = Label(
    type="country",
    id="country::IRL",
    value="Ireland",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_IRN = Label(
    type="country",
    id="country::IRN",
    value="Iran",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_IRQ = Label(
    type="country",
    id="country::IRQ",
    value="Iraq",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ISL = Label(
    type="country",
    id="country::ISL",
    value="Iceland",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_ISR = Label(
    type="country",
    id="country::ISR",
    value="Israel",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ITA = Label(
    type="country",
    id="country::ITA",
    value="Italy",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_JAM = Label(
    type="country",
    id="country::JAM",
    value="Jamaica",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_JOR = Label(
    type="country",
    id="country::JOR",
    value="Jordan",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_JPN = Label(
    type="country",
    id="country::JPN",
    value="Japan",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_KAZ = Label(
    type="country",
    id="country::KAZ",
    value="Kazakhstan",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_KEN = Label(
    type="country",
    id="country::KEN",
    value="Kenya",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_KGZ = Label(
    type="country",
    id="country::KGZ",
    value="Kyrgyzstan",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_KHM = Label(
    type="country",
    id="country::KHM",
    value="Cambodia",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_KIR = Label(
    type="country",
    id="country::KIR",
    value="Kiribati",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_KNA = Label(
    type="country",
    id="country::KNA",
    value="Saint Kitts and Nevis",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_KOR = Label(
    type="country",
    id="country::KOR",
    value="South Korea",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_KWT = Label(
    type="country",
    id="country::KWT",
    value="Kuwait",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_LAO = Label(
    type="country",
    id="country::LAO",
    value="Laos",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_LBN = Label(
    type="country",
    id="country::LBN",
    value="Lebanon",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_LBR = Label(
    type="country",
    id="country::LBR",
    value="Liberia",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_LBY = Label(
    type="country",
    id="country::LBY",
    value="Libya",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_LCA = Label(
    type="country",
    id="country::LCA",
    value="Saint Lucia",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_LIE = Label(
    type="country",
    id="country::LIE",
    value="Liechtenstein",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_LKA = Label(
    type="country",
    id="country::LKA",
    value="Sri Lanka",
    labels=[LabelRelationship(type="subconcept_of", value=region_SAS)],
)
country_LSO = Label(
    type="country",
    id="country::LSO",
    value="Lesotho",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_LTU = Label(
    type="country",
    id="country::LTU",
    value="Lithuania",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_LUX = Label(
    type="country",
    id="country::LUX",
    value="Luxembourg",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_LVA = Label(
    type="country",
    id="country::LVA",
    value="Latvia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_MAR = Label(
    type="country",
    id="country::MAR",
    value="Morocco",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_MCO = Label(
    type="country",
    id="country::MCO",
    value="Monaco",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_MDA = Label(
    type="country",
    id="country::MDA",
    value="Moldova",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_MDG = Label(
    type="country",
    id="country::MDG",
    value="Madagascar",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_MDV = Label(
    type="country",
    id="country::MDV",
    value="Maldives",
    labels=[LabelRelationship(type="subconcept_of", value=region_SAS)],
)
country_MEX = Label(
    type="country",
    id="country::MEX",
    value="Mexico",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_MHL = Label(
    type="country",
    id="country::MHL",
    value="Marshall Islands",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_MKD = Label(
    type="country",
    id="country::MKD",
    value="North Macedonia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_MLI = Label(
    type="country",
    id="country::MLI",
    value="Mali",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_MLT = Label(
    type="country",
    id="country::MLT",
    value="Malta",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_MMR = Label(
    type="country",
    id="country::MMR",
    value="Myanmar",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_MNE = Label(
    type="country",
    id="country::MNE",
    value="Montenegro",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_MNG = Label(
    type="country",
    id="country::MNG",
    value="Mongolia",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_MOZ = Label(
    type="country",
    id="country::MOZ",
    value="Mozambique",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_MRT = Label(
    type="country",
    id="country::MRT",
    value="Mauritania",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_MUS = Label(
    type="country",
    id="country::MUS",
    value="Mauritius",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_MWI = Label(
    type="country",
    id="country::MWI",
    value="Malawi",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_MYS = Label(
    type="country",
    id="country::MYS",
    value="Malaysia",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_NAM = Label(
    type="country",
    id="country::NAM",
    value="Namibia",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_NER = Label(
    type="country",
    id="country::NER",
    value="Niger",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_NGA = Label(
    type="country",
    id="country::NGA",
    value="Nigeria",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_NIC = Label(
    type="country",
    id="country::NIC",
    value="Nicaragua",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_NIU = Label(
    type="country",
    id="country::NIU",
    value="Niue",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_NLD = Label(
    type="country",
    id="country::NLD",
    value="Netherlands",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_NOR = Label(
    type="country",
    id="country::NOR",
    value="Norway",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_NPL = Label(
    type="country",
    id="country::NPL",
    value="Nepal",
    labels=[LabelRelationship(type="subconcept_of", value=region_SAS)],
)
country_NRU = Label(
    type="country",
    id="country::NRU",
    value="Nauru",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_NZL = Label(
    type="country",
    id="country::NZL",
    value="New Zealand",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_OMN = Label(
    type="country",
    id="country::OMN",
    value="Oman",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_PAK = Label(
    type="country",
    id="country::PAK",
    value="Pakistan",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_PAN = Label(
    type="country",
    id="country::PAN",
    value="Panama",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_PER = Label(
    type="country",
    id="country::PER",
    value="Peru",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_PHL = Label(
    type="country",
    id="country::PHL",
    value="Philippines",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_PLW = Label(
    type="country",
    id="country::PLW",
    value="Palau",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_PNG = Label(
    type="country",
    id="country::PNG",
    value="Papua New Guinea",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_POL = Label(
    type="country",
    id="country::POL",
    value="Poland",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_PRK = Label(
    type="country",
    id="country::PRK",
    value="North Korea",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_PRT = Label(
    type="country",
    id="country::PRT",
    value="Portugal",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_PRY = Label(
    type="country",
    id="country::PRY",
    value="Paraguay",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_PSE = Label(
    type="country",
    id="country::PSE",
    value="Palestine, State of",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_QAT = Label(
    type="country",
    id="country::QAT",
    value="Qatar",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ROU = Label(
    type="country",
    id="country::ROU",
    value="Romania",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_RUS = Label(
    type="country",
    id="country::RUS",
    value="Russian Federation",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_RWA = Label(
    type="country",
    id="country::RWA",
    value="Rwanda",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SAU = Label(
    type="country",
    id="country::SAU",
    value="Saudi Arabia",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_SDN = Label(
    type="country",
    id="country::SDN",
    value="Sudan",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SEN = Label(
    type="country",
    id="country::SEN",
    value="Senegal",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SGP = Label(
    type="country",
    id="country::SGP",
    value="Singapore",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_SLB = Label(
    type="country",
    id="country::SLB",
    value="Solomon Islands",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_SLE = Label(
    type="country",
    id="country::SLE",
    value="Sierra Leone",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SLV = Label(
    type="country",
    id="country::SLV",
    value="El Salvador",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_SMR = Label(
    type="country",
    id="country::SMR",
    value="San Marino",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_SOM = Label(
    type="country",
    id="country::SOM",
    value="Somalia",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SRB = Label(
    type="country",
    id="country::SRB",
    value="Serbia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_SSD = Label(
    type="country",
    id="country::SSD",
    value="South Sudan",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_STP = Label(
    type="country",
    id="country::STP",
    value="Sao Tome and Principe",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SUR = Label(
    type="country",
    id="country::SUR",
    value="Suriname",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_SVK = Label(
    type="country",
    id="country::SVK",
    value="Slovakia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_SVN = Label(
    type="country",
    id="country::SVN",
    value="Slovenia",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_SWE = Label(
    type="country",
    id="country::SWE",
    value="Sweden",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_SWZ = Label(
    type="country",
    id="country::SWZ",
    value="Eswatini",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SYC = Label(
    type="country",
    id="country::SYC",
    value="Seychelles",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_SYR = Label(
    type="country",
    id="country::SYR",
    value="Syria",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_TCD = Label(
    type="country",
    id="country::TCD",
    value="Chad",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_TGO = Label(
    type="country",
    id="country::TGO",
    value="Togo",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_THA = Label(
    type="country",
    id="country::THA",
    value="Thailand",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_TJK = Label(
    type="country",
    id="country::TJK",
    value="Tajikistan",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_TKM = Label(
    type="country",
    id="country::TKM",
    value="Turkmenistan",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_TLS = Label(
    type="country",
    id="country::TLS",
    value="Timor-Leste",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_TON = Label(
    type="country",
    id="country::TON",
    value="Tonga",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_TTO = Label(
    type="country",
    id="country::TTO",
    value="Trinidad and Tobago",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_TUN = Label(
    type="country",
    id="country::TUN",
    value="Tunisia",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_TUR = Label(
    type="country",
    id="country::TUR",
    value="Türkiye",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_TUV = Label(
    type="country",
    id="country::TUV",
    value="Tuvalu",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_TWN = Label(
    type="country",
    id="country::TWN",
    value="Taiwan",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_TZA = Label(
    type="country",
    id="country::TZA",
    value="Tanzania",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_UGA = Label(
    type="country",
    id="country::UGA",
    value="Uganda",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_UKR = Label(
    type="country",
    id="country::UKR",
    value="Ukraine",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_URY = Label(
    type="country",
    id="country::URY",
    value="Uruguay",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_USA = Label(
    type="country",
    id="country::USA",
    value="United States of America",
    labels=[LabelRelationship(type="subconcept_of", value=region_NAC)],
)
country_UZB = Label(
    type="country",
    id="country::UZB",
    value="Uzbekistan",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_VAT = Label(
    type="country",
    id="country::VAT",
    value="Holy See (Vatican City State)",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)
country_VCT = Label(
    type="country",
    id="country::VCT",
    value="Saint Vincent and the Grenadines",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_VEN = Label(
    type="country",
    id="country::VEN",
    value="Venezuela, Bolivarian Republic of",
    labels=[LabelRelationship(type="subconcept_of", value=region_LCN)],
)
country_VNM = Label(
    type="country",
    id="country::VNM",
    value="Viet Nam",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_VUT = Label(
    type="country",
    id="country::VUT",
    value="Vanuatu",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_WSM = Label(
    type="country",
    id="country::WSM",
    value="Samoa",
    labels=[LabelRelationship(type="subconcept_of", value=region_EAS)],
)
country_XAB = Label(type="country", id="country::XAB", value="International", labels=[])
country_YEM = Label(
    type="country",
    id="country::YEM",
    value="Yemen",
    labels=[LabelRelationship(type="subconcept_of", value=region_MEA)],
)
country_ZAF = Label(
    type="country",
    id="country::ZAF",
    value="South Africa",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_ZMB = Label(
    type="country",
    id="country::ZMB",
    value="Zambia",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)
country_ZWE = Label(
    type="country",
    id="country::ZWE",
    value="Zimbabwe",
    labels=[LabelRelationship(type="subconcept_of", value=region_SSF)],
)

# region subdivisions
subdivision_AR_Y = Label(
    type="subdivision",
    id="subdivision::AR-Y",
    value="Jujuy",
    labels=[LabelRelationship(type="subconcept_of", value=country_ARG)],
)
subdivision_AT_3 = Label(
    type="subdivision",
    id="subdivision::AT-3",
    value="Niederösterreich",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUT)],
)
subdivision_AT_4 = Label(
    type="subdivision",
    id="subdivision::AT-4",
    value="Oberösterreich",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUT)],
)
subdivision_AU_ACT = Label(
    type="subdivision",
    id="subdivision::AU-ACT",
    value="Australian Capital Territory",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUS)],
)
subdivision_AU_NSW = Label(
    type="subdivision",
    id="subdivision::AU-NSW",
    value="New South Wales",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUS)],
)
subdivision_AU_QLD = Label(
    type="subdivision",
    id="subdivision::AU-QLD",
    value="Queensland",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUS)],
)
subdivision_AU_SA = Label(
    type="subdivision",
    id="subdivision::AU-SA",
    value="South Australia",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUS)],
)
subdivision_AU_VIC = Label(
    type="subdivision",
    id="subdivision::AU-VIC",
    value="Victoria",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUS)],
)
subdivision_AU_WA = Label(
    type="subdivision",
    id="subdivision::AU-WA",
    value="Western Australia",
    labels=[LabelRelationship(type="subconcept_of", value=country_AUS)],
)
subdivision_BR_AC = Label(
    type="subdivision",
    id="subdivision::BR-AC",
    value="Acre",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_AL = Label(
    type="subdivision",
    id="subdivision::BR-AL",
    value="Alagoas",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_AM = Label(
    type="subdivision",
    id="subdivision::BR-AM",
    value="Amazonas",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_AP = Label(
    type="subdivision",
    id="subdivision::BR-AP",
    value="Amapá",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_BA = Label(
    type="subdivision",
    id="subdivision::BR-BA",
    value="Bahia",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_CE = Label(
    type="subdivision",
    id="subdivision::BR-CE",
    value="Ceará",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_DF = Label(
    type="subdivision",
    id="subdivision::BR-DF",
    value="Distrito Federal",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_ES = Label(
    type="subdivision",
    id="subdivision::BR-ES",
    value="Espírito Santo",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_GO = Label(
    type="subdivision",
    id="subdivision::BR-GO",
    value="Goiás",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_MA = Label(
    type="subdivision",
    id="subdivision::BR-MA",
    value="Maranhão",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_MG = Label(
    type="subdivision",
    id="subdivision::BR-MG",
    value="Minas Gerais",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_MS = Label(
    type="subdivision",
    id="subdivision::BR-MS",
    value="Mato Grosso do Sul",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_MT = Label(
    type="subdivision",
    id="subdivision::BR-MT",
    value="Mato Grosso",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_PA = Label(
    type="subdivision",
    id="subdivision::BR-PA",
    value="Pará",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_PB = Label(
    type="subdivision",
    id="subdivision::BR-PB",
    value="Paraíba",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_PE = Label(
    type="subdivision",
    id="subdivision::BR-PE",
    value="Pernambuco",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_PI = Label(
    type="subdivision",
    id="subdivision::BR-PI",
    value="Piauí",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_PR = Label(
    type="subdivision",
    id="subdivision::BR-PR",
    value="Paraná",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_RJ = Label(
    type="subdivision",
    id="subdivision::BR-RJ",
    value="Rio de Janeiro",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_RO = Label(
    type="subdivision",
    id="subdivision::BR-RO",
    value="Rondônia",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_RR = Label(
    type="subdivision",
    id="subdivision::BR-RR",
    value="Roraima",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_RS = Label(
    type="subdivision",
    id="subdivision::BR-RS",
    value="Rio Grande do Sul",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_SC = Label(
    type="subdivision",
    id="subdivision::BR-SC",
    value="Santa Catarina",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_SE = Label(
    type="subdivision",
    id="subdivision::BR-SE",
    value="Sergipe",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_SP = Label(
    type="subdivision",
    id="subdivision::BR-SP",
    value="São Paulo",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_BR_TO = Label(
    type="subdivision",
    id="subdivision::BR-TO",
    value="Tocantins",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)
subdivision_CA_BC = Label(
    type="subdivision",
    id="subdivision::CA-BC",
    value="British Columbia",
    labels=[LabelRelationship(type="subconcept_of", value=country_CAN)],
)
subdivision_CA_ON = Label(
    type="subdivision",
    id="subdivision::CA-ON",
    value="Ontario",
    labels=[LabelRelationship(type="subconcept_of", value=country_CAN)],
)
subdivision_CA_PE = Label(
    type="subdivision",
    id="subdivision::CA-PE",
    value="Prince Edward Island",
    labels=[LabelRelationship(type="subconcept_of", value=country_CAN)],
)
subdivision_CA_QC = Label(
    type="subdivision",
    id="subdivision::CA-QC",
    value="Quebec",
    labels=[LabelRelationship(type="subconcept_of", value=country_CAN)],
)
subdivision_CA_SK = Label(
    type="subdivision",
    id="subdivision::CA-SK",
    value="Saskatchewan",
    labels=[LabelRelationship(type="subconcept_of", value=country_CAN)],
)
subdivision_CL_RM = Label(
    type="subdivision",
    id="subdivision::CL-RM",
    value="Región Metropolitana de Santiago",
    labels=[LabelRelationship(type="subconcept_of", value=country_CHL)],
)
subdivision_CO_ANT = Label(
    type="subdivision",
    id="subdivision::CO-ANT",
    value="Antioquia",
    labels=[LabelRelationship(type="subconcept_of", value=country_COL)],
)
subdivision_CO_BOY = Label(
    type="subdivision",
    id="subdivision::CO-BOY",
    value="Boyacá",
    labels=[LabelRelationship(type="subconcept_of", value=country_COL)],
)
subdivision_CO_CAQ = Label(
    type="subdivision",
    id="subdivision::CO-CAQ",
    value="Caquetá",
    labels=[LabelRelationship(type="subconcept_of", value=country_COL)],
)
subdivision_CO_CUN = Label(
    type="subdivision",
    id="subdivision::CO-CUN",
    value="Cundinamarca",
    labels=[LabelRelationship(type="subconcept_of", value=country_COL)],
)
subdivision_CO_NAR = Label(
    type="subdivision",
    id="subdivision::CO-NAR",
    value="Nariño",
    labels=[LabelRelationship(type="subconcept_of", value=country_COL)],
)
subdivision_CV_CA = Label(
    type="subdivision",
    id="subdivision::CV-CA",
    value="Santa Catarina",
    labels=[LabelRelationship(type="subconcept_of", value=country_CPV)],
)
subdivision_DE_BE = Label(
    type="subdivision",
    id="subdivision::DE-BE",
    value="Berlin",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_DE_BW = Label(
    type="subdivision",
    id="subdivision::DE-BW",
    value="Baden-Württemberg",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_DE_BY = Label(
    type="subdivision",
    id="subdivision::DE-BY",
    value="Bayern",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_DE_HE = Label(
    type="subdivision",
    id="subdivision::DE-HE",
    value="Hessen",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_DE_NI = Label(
    type="subdivision",
    id="subdivision::DE-NI",
    value="Niedersachsen",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_DE_NW = Label(
    type="subdivision",
    id="subdivision::DE-NW",
    value="Nordrhein-Westfalen",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_DE_TH = Label(
    type="subdivision",
    id="subdivision::DE-TH",
    value="Thüringen",
    labels=[LabelRelationship(type="subconcept_of", value=country_DEU)],
)
subdivision_EC_Y = Label(
    type="subdivision",
    id="subdivision::EC-Y",
    value="Pastaza",
    labels=[LabelRelationship(type="subconcept_of", value=country_ECU)],
)
subdivision_ES_19572 = Label(
    type="subdivision",
    id="subdivision::ES-19572",
    value="Andalucía",
    labels=[LabelRelationship(type="subconcept_of", value=country_ESP)],
)
subdivision_ES_19574 = Label(
    type="subdivision",
    id="subdivision::ES-19574",
    value="Canarias",
    labels=[LabelRelationship(type="subconcept_of", value=country_ESP)],
)
subdivision_ES_CT = Label(
    type="subdivision",
    id="subdivision::ES-CT",
    value="Catalunya",
    labels=[LabelRelationship(type="subconcept_of", value=country_ESP)],
)
subdivision_ES_GA = Label(
    type="subdivision",
    id="subdivision::ES-GA",
    value="Galicia",
    labels=[LabelRelationship(type="subconcept_of", value=country_ESP)],
)
subdivision_ES_NA = Label(
    type="subdivision",
    id="subdivision::ES-NA",
    value="Navarra",
    labels=[LabelRelationship(type="subconcept_of", value=country_ESP)],
)
subdivision_ES_PV = Label(
    type="subdivision",
    id="subdivision::ES-PV",
    value="País Vasco",
    labels=[LabelRelationship(type="subconcept_of", value=country_ESP)],
)
subdivision_GB_NIR = Label(
    type="subdivision",
    id="subdivision::GB-NIR",
    value="Northern Ireland",
    labels=[LabelRelationship(type="subconcept_of", value=country_GBR)],
)
subdivision_GB_SCT = Label(
    type="subdivision",
    id="subdivision::GB-SCT",
    value="Scotland",
    labels=[LabelRelationship(type="subconcept_of", value=country_GBR)],
)
subdivision_GB_WLS = Label(
    type="subdivision",
    id="subdivision::GB-WLS",
    value="Wales",
    labels=[LabelRelationship(type="subconcept_of", value=country_GBR)],
)
subdivision_ID_KB = Label(
    type="subdivision",
    id="subdivision::ID-KB",
    value="Kalimantan Barat",
    labels=[LabelRelationship(type="subconcept_of", value=country_IDN)],
)
subdivision_ID_KI = Label(
    type="subdivision",
    id="subdivision::ID-KI",
    value="Kalimantan Timur",
    labels=[LabelRelationship(type="subconcept_of", value=country_IDN)],
)
subdivision_ID_KU = Label(
    type="subdivision",
    id="subdivision::ID-KU",
    value="North Kalimantan",
    labels=[LabelRelationship(type="subconcept_of", value=country_IDN)],
)
subdivision_ID_PA = Label(
    type="subdivision",
    id="subdivision::ID-PA",
    value="Papua",
    labels=[LabelRelationship(type="subconcept_of", value=country_IDN)],
)
subdivision_IN_AN = Label(
    type="subdivision",
    id="subdivision::IN-AN",
    value="Andaman and Nicobar Islands",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_AP = Label(
    type="subdivision",
    id="subdivision::IN-AP",
    value="Andhra Pradesh",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_AR = Label(
    type="subdivision",
    id="subdivision::IN-AR",
    value="Arunachal Pradesh",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_AS = Label(
    type="subdivision",
    id="subdivision::IN-AS",
    value="Assam",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_BR = Label(
    type="subdivision",
    id="subdivision::IN-BR",
    value="Bihar",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_CH = Label(
    type="subdivision",
    id="subdivision::IN-CH",
    value="Chandigarh",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_DL = Label(
    type="subdivision",
    id="subdivision::IN-DL",
    value="Delhi",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_GA = Label(
    type="subdivision",
    id="subdivision::IN-GA",
    value="Goa",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_GJ = Label(
    type="subdivision",
    id="subdivision::IN-GJ",
    value="Gujarat",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_HP = Label(
    type="subdivision",
    id="subdivision::IN-HP",
    value="Himachal Pradesh",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_HR = Label(
    type="subdivision",
    id="subdivision::IN-HR",
    value="Haryana",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_JH = Label(
    type="subdivision",
    id="subdivision::IN-JH",
    value="Jharkhand",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_JK = Label(
    type="subdivision",
    id="subdivision::IN-JK",
    value="Jammu and Kashmir",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_KL = Label(
    type="subdivision",
    id="subdivision::IN-KL",
    value="Kerala",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_LD = Label(
    type="subdivision",
    id="subdivision::IN-LD",
    value="Lakshadweep",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_MH = Label(
    type="subdivision",
    id="subdivision::IN-MH",
    value="Maharashtra",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_ML = Label(
    type="subdivision",
    id="subdivision::IN-ML",
    value="Meghalaya",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_MP = Label(
    type="subdivision",
    id="subdivision::IN-MP",
    value="Madhya Pradesh",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_MZ = Label(
    type="subdivision",
    id="subdivision::IN-MZ",
    value="Mizoram",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_NL = Label(
    type="subdivision",
    id="subdivision::IN-NL",
    value="Nagaland",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_OD = Label(
    type="subdivision",
    id="subdivision::IN-OD",
    value="Odisha",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_PB = Label(
    type="subdivision",
    id="subdivision::IN-PB",
    value="Punjab",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_PY = Label(
    type="subdivision",
    id="subdivision::IN-PY",
    value="Puducherry",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_RJ = Label(
    type="subdivision",
    id="subdivision::IN-RJ",
    value="Rajasthan",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_SK = Label(
    type="subdivision",
    id="subdivision::IN-SK",
    value="Sikkim",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_TG = Label(
    type="subdivision",
    id="subdivision::IN-TG",
    value="Telangana",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_TN = Label(
    type="subdivision",
    id="subdivision::IN-TN",
    value="Tamil Nadu",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_UP = Label(
    type="subdivision",
    id="subdivision::IN-UP",
    value="Uttar Pradesh",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_UT = Label(
    type="subdivision",
    id="subdivision::IN-UT",
    value="Uttarakhand",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IN_WB = Label(
    type="subdivision",
    id="subdivision::IN-WB",
    value="West Bengal",
    labels=[LabelRelationship(type="subconcept_of", value=country_IND)],
)
subdivision_IT_21 = Label(
    type="subdivision",
    id="subdivision::IT-21",
    value="Piemonte",
    labels=[LabelRelationship(type="subconcept_of", value=country_ITA)],
)
subdivision_IT_25 = Label(
    type="subdivision",
    id="subdivision::IT-25",
    value="Lombardia",
    labels=[LabelRelationship(type="subconcept_of", value=country_ITA)],
)
subdivision_MX_AGU = Label(
    type="subdivision",
    id="subdivision::MX-AGU",
    value="Aguascalientes",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_BCN = Label(
    type="subdivision",
    id="subdivision::MX-BCN",
    value="Baja California",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_BCS = Label(
    type="subdivision",
    id="subdivision::MX-BCS",
    value="Baja California Sur",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_CAM = Label(
    type="subdivision",
    id="subdivision::MX-CAM",
    value="Campeche",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_CHH = Label(
    type="subdivision",
    id="subdivision::MX-CHH",
    value="Chihuahua",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_CHP = Label(
    type="subdivision",
    id="subdivision::MX-CHP",
    value="Chiapas",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_CMX = Label(
    type="subdivision",
    id="subdivision::MX-CMX",
    value="Mexico City",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_GUA = Label(
    type="subdivision",
    id="subdivision::MX-GUA",
    value="Guanajuato",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_HID = Label(
    type="subdivision",
    id="subdivision::MX-HID",
    value="Hidalgo",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_JAL = Label(
    type="subdivision",
    id="subdivision::MX-JAL",
    value="Jalisco",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_NLE = Label(
    type="subdivision",
    id="subdivision::MX-NLE",
    value="Nuevo León",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_OAX = Label(
    type="subdivision",
    id="subdivision::MX-OAX",
    value="Oaxaca",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_PUE = Label(
    type="subdivision",
    id="subdivision::MX-PUE",
    value="Puebla",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_QUE = Label(
    type="subdivision",
    id="subdivision::MX-QUE",
    value="Querétaro",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_ROO = Label(
    type="subdivision",
    id="subdivision::MX-ROO",
    value="Quintana Roo",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_SON = Label(
    type="subdivision",
    id="subdivision::MX-SON",
    value="Sonora",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_TAB = Label(
    type="subdivision",
    id="subdivision::MX-TAB",
    value="Tabasco",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_YUC = Label(
    type="subdivision",
    id="subdivision::MX-YUC",
    value="Yucatán",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_MX_ZAC = Label(
    type="subdivision",
    id="subdivision::MX-ZAC",
    value="Zacatecas",
    labels=[LabelRelationship(type="subconcept_of", value=country_MEX)],
)
subdivision_PE_AMA = Label(
    type="subdivision",
    id="subdivision::PE-AMA",
    value="Amazonas",
    labels=[LabelRelationship(type="subconcept_of", value=country_PER)],
)
subdivision_PT_20 = Label(
    type="subdivision",
    id="subdivision::PT-20",
    value="Azores",
    labels=[LabelRelationship(type="subconcept_of", value=country_PRT)],
)
subdivision_PT_30 = Label(
    type="subdivision",
    id="subdivision::PT-30",
    value="Região Autónoma da Madeira",
    labels=[LabelRelationship(type="subconcept_of", value=country_PRT)],
)
subdivision_TH_50 = Label(
    type="subdivision",
    id="subdivision::TH-50",
    value="Chiang Mai",
    labels=[LabelRelationship(type="subconcept_of", value=country_THA)],
)
subdivision_US_AK = Label(
    type="subdivision",
    id="subdivision::US-AK",
    value="Alaska",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_AL = Label(
    type="subdivision",
    id="subdivision::US-AL",
    value="Alabama",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_AR = Label(
    type="subdivision",
    id="subdivision::US-AR",
    value="Arkansas",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_AZ = Label(
    type="subdivision",
    id="subdivision::US-AZ",
    value="Arizona",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_CA = Label(
    type="subdivision",
    id="subdivision::US-CA",
    value="California",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_CO = Label(
    type="subdivision",
    id="subdivision::US-CO",
    value="Colorado",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_CT = Label(
    type="subdivision",
    id="subdivision::US-CT",
    value="Connecticut",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_DC = Label(
    type="subdivision",
    id="subdivision::US-DC",
    value="District of Columbia",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_DE = Label(
    type="subdivision",
    id="subdivision::US-DE",
    value="Delaware",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_FL = Label(
    type="subdivision",
    id="subdivision::US-FL",
    value="Florida",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_GA = Label(
    type="subdivision",
    id="subdivision::US-GA",
    value="Georgia",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_GU = Label(
    type="subdivision",
    id="subdivision::US-GU",
    value="Guam",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_HI = Label(
    type="subdivision",
    id="subdivision::US-HI",
    value="Hawaii",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_IA = Label(
    type="subdivision",
    id="subdivision::US-IA",
    value="Iowa",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_ID = Label(
    type="subdivision",
    id="subdivision::US-ID",
    value="Idaho",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_IL = Label(
    type="subdivision",
    id="subdivision::US-IL",
    value="Illinois",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_IN = Label(
    type="subdivision",
    id="subdivision::US-IN",
    value="Indiana",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_KS = Label(
    type="subdivision",
    id="subdivision::US-KS",
    value="Kansas",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_KY = Label(
    type="subdivision",
    id="subdivision::US-KY",
    value="Kentucky",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_LA = Label(
    type="subdivision",
    id="subdivision::US-LA",
    value="Louisiana",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MA = Label(
    type="subdivision",
    id="subdivision::US-MA",
    value="Massachusetts",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MD = Label(
    type="subdivision",
    id="subdivision::US-MD",
    value="Maryland",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_ME = Label(
    type="subdivision",
    id="subdivision::US-ME",
    value="Maine",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MI = Label(
    type="subdivision",
    id="subdivision::US-MI",
    value="Michigan",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MN = Label(
    type="subdivision",
    id="subdivision::US-MN",
    value="Minnesota",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MO = Label(
    type="subdivision",
    id="subdivision::US-MO",
    value="Missouri",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MS = Label(
    type="subdivision",
    id="subdivision::US-MS",
    value="Mississippi",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_MT = Label(
    type="subdivision",
    id="subdivision::US-MT",
    value="Montana",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NC = Label(
    type="subdivision",
    id="subdivision::US-NC",
    value="North Carolina",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_ND = Label(
    type="subdivision",
    id="subdivision::US-ND",
    value="North Dakota",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NE = Label(
    type="subdivision",
    id="subdivision::US-NE",
    value="Nebraska",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NH = Label(
    type="subdivision",
    id="subdivision::US-NH",
    value="New Hampshire",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NJ = Label(
    type="subdivision",
    id="subdivision::US-NJ",
    value="New Jersey",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NM = Label(
    type="subdivision",
    id="subdivision::US-NM",
    value="New Mexico",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NV = Label(
    type="subdivision",
    id="subdivision::US-NV",
    value="Nevada",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_NY = Label(
    type="subdivision",
    id="subdivision::US-NY",
    value="New York",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_OH = Label(
    type="subdivision",
    id="subdivision::US-OH",
    value="Ohio",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_OK = Label(
    type="subdivision",
    id="subdivision::US-OK",
    value="Oklahoma",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_OR = Label(
    type="subdivision",
    id="subdivision::US-OR",
    value="Oregon",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_PA = Label(
    type="subdivision",
    id="subdivision::US-PA",
    value="Pennsylvania",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_PR = Label(
    type="subdivision",
    id="subdivision::US-PR",
    value="Puerto Rico",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_RI = Label(
    type="subdivision",
    id="subdivision::US-RI",
    value="Rhode Island",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_SC = Label(
    type="subdivision",
    id="subdivision::US-SC",
    value="South Carolina",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_SD = Label(
    type="subdivision",
    id="subdivision::US-SD",
    value="South Dakota",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_TN = Label(
    type="subdivision",
    id="subdivision::US-TN",
    value="Tennessee",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_TX = Label(
    type="subdivision",
    id="subdivision::US-TX",
    value="Texas",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_UT = Label(
    type="subdivision",
    id="subdivision::US-UT",
    value="Utah",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_VA = Label(
    type="subdivision",
    id="subdivision::US-VA",
    value="Virginia",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_VI = Label(
    type="subdivision",
    id="subdivision::US-VI",
    value="Virgin Islands, U.S.",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_VT = Label(
    type="subdivision",
    id="subdivision::US-VT",
    value="Vermont",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_WA = Label(
    type="subdivision",
    id="subdivision::US-WA",
    value="Washington",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_WI = Label(
    type="subdivision",
    id="subdivision::US-WI",
    value="Wisconsin",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_WV = Label(
    type="subdivision",
    id="subdivision::US-WV",
    value="West Virginia",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_US_WY = Label(
    type="subdivision",
    id="subdivision::US-WY",
    value="Wyoming",
    labels=[LabelRelationship(type="subconcept_of", value=country_USA)],
)
subdivision_ZA_GP = Label(
    type="subdivision",
    id="subdivision::ZA-GP",
    value="Gauteng",
    labels=[LabelRelationship(type="subconcept_of", value=country_ZAF)],
)
subdivision_ZA_NL = Label(
    type="subdivision",
    id="subdivision::ZA-NL",
    value="Kwazulu-Natal",
    labels=[LabelRelationship(type="subconcept_of", value=country_ZAF)],
)
subdivision_ZA_WC = Label(
    type="subdivision",
    id="subdivision::ZA-WC",
    value="Western Cape",
    labels=[LabelRelationship(type="subconcept_of", value=country_ZAF)],
)

# The three below are confirmed in use on valid, published documents but are
# missing from `published.labels`.

# Not in the Snowflake table; tagged on real, published Sabin litigation docs
# (e.g. Sabin.family.134140.0, Sabin.family.134136.0).
subdivision_BR_RN = Label(
    type="subdivision",
    id="subdivision::BR-RN",
    value="Rio Grande do Norte",
    labels=[LabelRelationship(type="subconcept_of", value=country_BRA)],
)

# Not in the Snowflake table; tagged on a real, published Sabin litigation doc
# (Sabin.family.16944.0).
subdivision_CA_NS = Label(
    type="subdivision",
    id="subdivision::CA-NS",
    value="Nova Scotia",
    labels=[LabelRelationship(type="subconcept_of", value=country_CAN)],
)

# Not in the Snowflake table; comes from the admin service (CCLW/CPR national
# law documents, e.g. CCLW.family.i00000218.n0000, CPR.family.i00002239.n0000).
country_XKX = Label(
    type="country",
    id="country::XKX",
    value="Kosovo",
    labels=[LabelRelationship(type="subconcept_of", value=region_ECS)],
)


geographies_taxonomy = [
    region_EAS,
    region_ECS,
    region_LCN,
    region_MEA,
    region_NAC,
    region_SAS,
    region_SSF,
    country_AFG,
    country_AGO,
    country_ALB,
    country_AND,
    country_ARE,
    country_ARG,
    country_ARM,
    country_ATG,
    country_AUS,
    country_AUT,
    country_AZE,
    country_BDI,
    country_BEL,
    country_BEN,
    country_BFA,
    country_BGD,
    country_BGR,
    country_BHR,
    country_BHS,
    country_BIH,
    country_BLR,
    country_BLZ,
    country_BOL,
    country_BRA,
    country_BRB,
    country_BRN,
    country_BTN,
    country_BWA,
    country_CAF,
    country_CAN,
    country_CHE,
    country_CHL,
    country_CHN,
    country_CIV,
    country_CMR,
    country_COD,
    country_COG,
    country_COK,
    country_COL,
    country_COM,
    country_CPV,
    country_CRI,
    country_CUB,
    country_CYM,
    country_CYP,
    country_CZE,
    country_DEU,
    country_DJI,
    country_DMA,
    country_DNK,
    country_DOM,
    country_DZA,
    country_ECU,
    country_EGY,
    country_ERI,
    country_ESP,
    country_EST,
    country_ETH,
    country_EUR,
    country_FIN,
    country_FJI,
    country_FRA,
    country_FSM,
    country_GAB,
    country_GBR,
    country_GEO,
    country_GHA,
    country_GIN,
    country_GMB,
    country_GNB,
    country_GNQ,
    country_GRC,
    country_GRD,
    country_GRL,
    country_GTM,
    country_GUY,
    country_HKG,
    country_HND,
    country_HRV,
    country_HTI,
    country_HUN,
    country_IDN,
    country_IMN,
    country_IND,
    country_IRL,
    country_IRN,
    country_IRQ,
    country_ISL,
    country_ISR,
    country_ITA,
    country_JAM,
    country_JOR,
    country_JPN,
    country_KAZ,
    country_KEN,
    country_KGZ,
    country_KHM,
    country_KIR,
    country_KNA,
    country_KOR,
    country_KWT,
    country_LAO,
    country_LBN,
    country_LBR,
    country_LBY,
    country_LCA,
    country_LIE,
    country_LKA,
    country_LSO,
    country_LTU,
    country_LUX,
    country_LVA,
    country_MAR,
    country_MCO,
    country_MDA,
    country_MDG,
    country_MDV,
    country_MEX,
    country_MHL,
    country_MKD,
    country_MLI,
    country_MLT,
    country_MMR,
    country_MNE,
    country_MNG,
    country_MOZ,
    country_MRT,
    country_MUS,
    country_MWI,
    country_MYS,
    country_NAM,
    country_NER,
    country_NGA,
    country_NIC,
    country_NIU,
    country_NLD,
    country_NOR,
    country_NPL,
    country_NRU,
    country_NZL,
    country_OMN,
    country_PAK,
    country_PAN,
    country_PER,
    country_PHL,
    country_PLW,
    country_PNG,
    country_POL,
    country_PRK,
    country_PRT,
    country_PRY,
    country_PSE,
    country_QAT,
    country_ROU,
    country_RUS,
    country_RWA,
    country_SAU,
    country_SDN,
    country_SEN,
    country_SGP,
    country_SLB,
    country_SLE,
    country_SLV,
    country_SMR,
    country_SOM,
    country_SRB,
    country_SSD,
    country_STP,
    country_SUR,
    country_SVK,
    country_SVN,
    country_SWE,
    country_SWZ,
    country_SYC,
    country_SYR,
    country_TCD,
    country_TGO,
    country_THA,
    country_TJK,
    country_TKM,
    country_TLS,
    country_TON,
    country_TTO,
    country_TUN,
    country_TUR,
    country_TUV,
    country_TWN,
    country_TZA,
    country_UGA,
    country_UKR,
    country_URY,
    country_USA,
    country_UZB,
    country_VAT,
    country_VCT,
    country_VEN,
    country_VNM,
    country_VUT,
    country_WSM,
    country_XAB,
    country_YEM,
    country_ZAF,
    country_ZMB,
    country_ZWE,
    subdivision_AR_Y,
    subdivision_AT_3,
    subdivision_AT_4,
    subdivision_AU_ACT,
    subdivision_AU_NSW,
    subdivision_AU_QLD,
    subdivision_AU_SA,
    subdivision_AU_VIC,
    subdivision_AU_WA,
    subdivision_BR_AC,
    subdivision_BR_AL,
    subdivision_BR_AM,
    subdivision_BR_AP,
    subdivision_BR_BA,
    subdivision_BR_CE,
    subdivision_BR_DF,
    subdivision_BR_ES,
    subdivision_BR_GO,
    subdivision_BR_MA,
    subdivision_BR_MG,
    subdivision_BR_MS,
    subdivision_BR_MT,
    subdivision_BR_PA,
    subdivision_BR_PB,
    subdivision_BR_PE,
    subdivision_BR_PI,
    subdivision_BR_PR,
    subdivision_BR_RJ,
    subdivision_BR_RO,
    subdivision_BR_RR,
    subdivision_BR_RS,
    subdivision_BR_SC,
    subdivision_BR_SE,
    subdivision_BR_SP,
    subdivision_BR_TO,
    subdivision_CA_BC,
    subdivision_CA_ON,
    subdivision_CA_PE,
    subdivision_CA_QC,
    subdivision_CA_SK,
    subdivision_CL_RM,
    subdivision_CO_ANT,
    subdivision_CO_BOY,
    subdivision_CO_CAQ,
    subdivision_CO_CUN,
    subdivision_CO_NAR,
    subdivision_CV_CA,
    subdivision_DE_BE,
    subdivision_DE_BW,
    subdivision_DE_BY,
    subdivision_DE_HE,
    subdivision_DE_NI,
    subdivision_DE_NW,
    subdivision_DE_TH,
    subdivision_EC_Y,
    subdivision_ES_19572,
    subdivision_ES_19574,
    subdivision_ES_CT,
    subdivision_ES_GA,
    subdivision_ES_NA,
    subdivision_ES_PV,
    subdivision_GB_NIR,
    subdivision_GB_SCT,
    subdivision_GB_WLS,
    subdivision_ID_KB,
    subdivision_ID_KI,
    subdivision_ID_KU,
    subdivision_ID_PA,
    subdivision_IN_AN,
    subdivision_IN_AP,
    subdivision_IN_AR,
    subdivision_IN_AS,
    subdivision_IN_BR,
    subdivision_IN_CH,
    subdivision_IN_DL,
    subdivision_IN_GA,
    subdivision_IN_GJ,
    subdivision_IN_HP,
    subdivision_IN_HR,
    subdivision_IN_JH,
    subdivision_IN_JK,
    subdivision_IN_KL,
    subdivision_IN_LD,
    subdivision_IN_MH,
    subdivision_IN_ML,
    subdivision_IN_MP,
    subdivision_IN_MZ,
    subdivision_IN_NL,
    subdivision_IN_OD,
    subdivision_IN_PB,
    subdivision_IN_PY,
    subdivision_IN_RJ,
    subdivision_IN_SK,
    subdivision_IN_TG,
    subdivision_IN_TN,
    subdivision_IN_UP,
    subdivision_IN_UT,
    subdivision_IN_WB,
    subdivision_IT_21,
    subdivision_IT_25,
    subdivision_MX_AGU,
    subdivision_MX_BCN,
    subdivision_MX_BCS,
    subdivision_MX_CAM,
    subdivision_MX_CHH,
    subdivision_MX_CHP,
    subdivision_MX_CMX,
    subdivision_MX_GUA,
    subdivision_MX_HID,
    subdivision_MX_JAL,
    subdivision_MX_NLE,
    subdivision_MX_OAX,
    subdivision_MX_PUE,
    subdivision_MX_QUE,
    subdivision_MX_ROO,
    subdivision_MX_SON,
    subdivision_MX_TAB,
    subdivision_MX_YUC,
    subdivision_MX_ZAC,
    subdivision_PE_AMA,
    subdivision_PT_20,
    subdivision_PT_30,
    subdivision_TH_50,
    subdivision_US_AK,
    subdivision_US_AL,
    subdivision_US_AR,
    subdivision_US_AZ,
    subdivision_US_CA,
    subdivision_US_CO,
    subdivision_US_CT,
    subdivision_US_DC,
    subdivision_US_DE,
    subdivision_US_FL,
    subdivision_US_GA,
    subdivision_US_GU,
    subdivision_US_HI,
    subdivision_US_IA,
    subdivision_US_ID,
    subdivision_US_IL,
    subdivision_US_IN,
    subdivision_US_KS,
    subdivision_US_KY,
    subdivision_US_LA,
    subdivision_US_MA,
    subdivision_US_MD,
    subdivision_US_ME,
    subdivision_US_MI,
    subdivision_US_MN,
    subdivision_US_MO,
    subdivision_US_MS,
    subdivision_US_MT,
    subdivision_US_NC,
    subdivision_US_ND,
    subdivision_US_NE,
    subdivision_US_NH,
    subdivision_US_NJ,
    subdivision_US_NM,
    subdivision_US_NV,
    subdivision_US_NY,
    subdivision_US_OH,
    subdivision_US_OK,
    subdivision_US_OR,
    subdivision_US_PA,
    subdivision_US_PR,
    subdivision_US_RI,
    subdivision_US_SC,
    subdivision_US_SD,
    subdivision_US_TN,
    subdivision_US_TX,
    subdivision_US_UT,
    subdivision_US_VA,
    subdivision_US_VI,
    subdivision_US_VT,
    subdivision_US_WA,
    subdivision_US_WI,
    subdivision_US_WV,
    subdivision_US_WY,
    subdivision_ZA_GP,
    subdivision_ZA_NL,
    subdivision_ZA_WC,
    subdivision_BR_RN,
    subdivision_CA_NS,
    country_XKX,
]
