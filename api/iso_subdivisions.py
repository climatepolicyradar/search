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

# ISO appends alternative names in brackets, e.g. "Wales [Cymru GB-CYM]".
BRACKETED_SUFFIX = re.compile(r"\s*\[.*\]\s*$")


def with_iso_subdivisions(existing: Sequence[Label]) -> list[Label]:
    """Return `existing` followed by the ISO subdivisions of its countries it lacks."""
    labels_by_id = {label.id: label for label in existing}
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

        added.append(
            Label(
                id=label_id,
                type="subdivision",
                value=BRACKETED_SUFFIX.sub("", subdivision.name),
                labels=[LabelRelationship(type="subconcept_of", value=country)],
            )
        )

    return [*existing, *added]
