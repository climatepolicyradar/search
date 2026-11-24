"""
Adds the ISO 3166-2 subdivisions that have no documents to the geographies taxonomy.

The labels in `geographies_taxonomy.py` only cover geographies that have documents,
so a country page cannot list the subdivisions that have none (to grey them out).
Only subdivisions are added: the countries stay as they are, since a country with no
documents is never linked to. Each subdivision goes flat under its country, as the
geographies-api lists them, and only for countries that are already in the taxonomy.

This is a stopgap. Once the taxonomy is fed from Snowflake, which holds every
geography, this file can go.
"""

import re
from collections.abc import Sequence

import pycountry

from search.data_in_models import Label, LabelRelationship

# Subdivisions that the documents are tagged with under an id that is not their ISO
# code, mapped to the ISO code. Both are in the taxonomy for now, so each of these
# appears twice and the ISO one counts no documents.
#
# TODO: once enrichment has retagged these documents with the ISO code, remove the
# legacy labels from `snowflake_geographies` (in `geographies_taxonomy.py`), and
# remove them from here.
LEGACY_SUBDIVISION_IDS = {
    "subdivision::ES-19572": "subdivision::ES-AN",
    "subdivision::ES-19574": "subdivision::ES-CN",
    "subdivision::IN-TG": "subdivision::IN-TS",
    "subdivision::IN-UT": "subdivision::IN-UK",
    "subdivision::ZA-NL": "subdivision::ZA-KZN",
}

# ISO appends alternative names in brackets, e.g. "Wales [Cymru GB-CYM]".
BRACKETED_SUFFIX = re.compile(r"\s*\[.*\]\s*$")


def with_iso_subdivisions(existing: Sequence[Label]) -> list[Label]:
    """Return `existing` followed by the ISO subdivisions of its countries it lacks."""
    labels_by_id = {label.id: label for label in existing}
    legacy_ids = {
        iso_id: legacy_id for legacy_id, iso_id in LEGACY_SUBDIVISION_IDS.items()
    }
    countries_by_alpha_2 = {
        country.alpha_2: labels_by_id[f"country::{country.alpha_3}"]
        for country in pycountry.countries
        if f"country::{country.alpha_3}" in labels_by_id
    }

    added: list[Label] = []
    for subdivision in sorted(pycountry.subdivisions, key=lambda s: s.code):
        label_id = f"subdivision::{subdivision.code}"
        country = countries_by_alpha_2.get(subdivision.country_code)
        if country is None or label_id in labels_by_id:
            continue

        # An ISO twin of a legacy label takes the legacy label's name, so the country
        # page does not list the same subdivision under two spellings.
        legacy = labels_by_id.get(legacy_ids.get(label_id, ""))
        value = legacy.value if legacy else BRACKETED_SUFFIX.sub("", subdivision.name)

        added.append(
            Label(
                id=label_id,
                type="subdivision",
                value=value,
                labels=[LabelRelationship(type="subconcept_of", value=country)],
            )
        )

    return [*existing, *added]
