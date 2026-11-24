from collections import Counter

import pytest

from api.geographies_taxonomy import geographies_taxonomy, snowflake_geographies
from api.iso_subdivisions import LEGACY_SUBDIVISION_IDS
from api.taxonomy.models import select, tree
from search.label import LabelSearchResult

BY_ID = {label.id: label for label in geographies_taxonomy}


def parent_ids(label_id: str) -> list[str]:
    return [relationship.value.id for relationship in BY_ID[label_id].labels]


def test_ids_are_unique():
    duplicated = [
        id
        for id, n in Counter(label.id for label in geographies_taxonomy).items()
        if n > 1
    ]

    assert duplicated == []


def test_existing_labels_are_unchanged():
    for label in snowflake_geographies:
        assert BY_ID[label.id] is label


def test_no_countries_are_added():
    """A country with no documents is never linked to, so only subdivisions are patched."""
    added = geographies_taxonomy[len(snowflake_geographies) :]

    assert {label.type for label in added} == {"subdivision"}
    assert "country::ABW" not in BY_ID


def test_subdivisions_of_countries_not_in_the_taxonomy_are_not_added():
    # Bonaire, Sint Eustatius and Saba is not a country in the taxonomy.
    assert "subdivision::BQ-BO" not in BY_ID


def test_new_subdivision_hangs_under_its_country():
    assert parent_ids("subdivision::MX-AGU") == ["country::MEX"]


def test_nested_subdivision_is_flat_under_its_country():
    # Almería is a province of Andalucía (ES-AN), but the geographies-api lists every
    # subdivision directly under the country, as do the existing labels.
    assert parent_ids("subdivision::ES-AL") == ["country::ESP"]


def test_every_subdivision_is_directly_under_a_country():
    for label in geographies_taxonomy:
        if label.type != "subdivision":
            continue

        assert len(label.labels) == 1, label.id
        assert label.labels[0].value.type == "country", label.id


@pytest.mark.parametrize(("legacy_id", "iso_id"), LEGACY_SUBDIVISION_IDS.items())
def test_legacy_subdivision_ids_are_kept_alongside_their_iso_codes(
    legacy_id: str, iso_id: str
):
    """Until the documents are retagged, both are listed, and the ISO one is the one with no documents."""
    assert legacy_id in BY_ID
    assert iso_id in BY_ID
    assert parent_ids(legacy_id) == parent_ids(iso_id)


@pytest.mark.parametrize(("legacy_id", "iso_id"), LEGACY_SUBDIVISION_IDS.items())
def test_iso_twin_of_a_legacy_subdivision_takes_the_legacy_name(
    legacy_id: str, iso_id: str
):
    # pycountry spells these "Telangāna" and "Uttarākhand".
    assert BY_ID[iso_id].value == BY_ID[legacy_id].value


def test_pycountry_name_artefacts_are_stripped():
    assert BY_ID["subdivision::GB-WLS"].value == "Wales"


def test_taxonomy_select_lists_every_subdivision_of_a_country():
    """What the country page's subdivision block asks for."""
    labels = [
        LabelSearchResult(
            id=label.id, type=label.type, value=label.value, labels=label.labels
        )
        for label in geographies_taxonomy
    ]

    [region] = select(tree(labels), ["**/country::MEX/subdivision::*"])
    [mexico] = region.children

    assert mexico.id == "country::MEX"
    assert len(mexico.children) == 32
    assert "subdivision::MX-ROO" in {child.id for child in mexico.children}
