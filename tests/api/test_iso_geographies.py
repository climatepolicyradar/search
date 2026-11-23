from collections import Counter

import pytest

from api.geographies_taxonomy import geographies_taxonomy, snowflake_geographies
from api.iso_geographies import (
    LEGACY_SUBDIVISION_IDS,
    DuplicateLabelError,
    UnknownParentError,
    with_iso_geographies,
)
from api.taxonomy.models import select, tree
from search.data_in_models import Label, LabelRelationship
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


def test_every_iso_country_is_present():
    countries = [label for label in geographies_taxonomy if label.type == "country"]

    # 249 ISO 3166-1 countries, plus International, European Union and Kosovo.
    assert len(countries) == 252


def test_existing_labels_are_unchanged():
    for label in snowflake_geographies:
        assert BY_ID[label.id] is label


def test_new_country_takes_its_world_bank_region():
    assert parent_ids("country::ABW") == ["region::LCN"]
    assert BY_ID["country::ABW"].value == "Aruba"


def test_new_country_without_a_world_bank_region_has_no_parent():
    assert parent_ids("country::ATA") == []


def test_new_country_without_a_common_name_uses_the_iso_name():
    assert BY_ID["country::ATF"].value == "French Southern Territories"


def test_existing_country_names_win_over_iso_names():
    # ISO calls this "Korea, Republic of".
    assert BY_ID["country::KOR"].value == "South Korea"


def test_new_top_level_subdivision_hangs_under_its_country():
    assert parent_ids("subdivision::MX-AGU") == ["country::MEX"]


def test_nested_subdivision_hangs_under_its_parent_subdivision():
    # Almería is a province of Andalucía, whose ISO code is ES-AN.
    assert parent_ids("subdivision::ES-AL") == ["subdivision::ES-AN"]


def test_every_subdivision_reaches_a_country_through_subdivisions_only():
    for label in geographies_taxonomy:
        if label.type != "subdivision":
            continue

        current = label
        while current.type == "subdivision":
            assert len(current.labels) == 1, current.id
            current = current.labels[0].value

        assert current.type == "country", label.id


@pytest.mark.parametrize(("legacy_id", "iso_id"), LEGACY_SUBDIVISION_IDS.items())
def test_legacy_subdivision_ids_are_kept_alongside_their_iso_codes(
    legacy_id: str, iso_id: str
):
    """Until the documents are retagged, both are listed, and the ISO one is the one with no documents."""
    assert legacy_id in BY_ID
    assert iso_id in BY_ID
    assert parent_ids(legacy_id) == parent_ids(iso_id)


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


def country(code: str, parent: Label | None = None) -> Label:
    labels = [LabelRelationship(type="subconcept_of", value=parent)] if parent else []
    return Label(type="country", id=f"country::{code}", value=code, labels=labels)


def test_a_subdivision_whose_parent_is_unknown_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("api.iso_geographies.ISO_COUNTRIES", [])
    monkeypatch.setattr(
        "api.iso_geographies.ISO_SUBDIVISIONS",
        [("subdivision::XX-1", "One", "country::XXX")],
    )

    with pytest.raises(UnknownParentError):
        with_iso_geographies([])


def test_a_label_that_is_already_known_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "api.iso_geographies.ISO_COUNTRIES", [("country::XXX", "Xland", None)]
    )
    monkeypatch.setattr("api.iso_geographies.ISO_SUBDIVISIONS", [])

    with pytest.raises(DuplicateLabelError):
        with_iso_geographies([country("XXX")])
