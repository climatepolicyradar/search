import pytest

from api.geographies_taxonomy import geographies_taxonomy

BY_ID = {label.id: label for label in geographies_taxonomy}


def test_ids_are_unique() -> None:
    assert len(BY_ID) == len(geographies_taxonomy)


@pytest.mark.parametrize(
    ("legacy_id", "iso_id"),
    [
        ("subdivision::ES-19572", "subdivision::ES-AN"),
        ("subdivision::ES-19574", "subdivision::ES-CN"),
        ("subdivision::IN-TG", "subdivision::IN-TS"),
        ("subdivision::IN-UT", "subdivision::IN-UK"),
        ("subdivision::ZA-NL", "subdivision::ZA-KZN"),
    ],
)
def test_retagged_subdivisions_are_listed_only_by_iso_code(
    legacy_id: str,
    iso_id: str,
) -> None:
    assert legacy_id not in BY_ID and iso_id in BY_ID


def test_every_iso_subdivision_of_a_country_is_flat_under_it() -> None:
    spain = [label for label in geographies_taxonomy if label.labels and label.labels[0].value.id == "country::ESP"]
    assert len(spain) == 69


def test_subdivision_name_overrides_win_over_iso_names() -> None:
    assert BY_ID["subdivision::IN-MH"].value == "Maharashtra"


def test_iso_bracketed_alternative_names_are_stripped() -> None:
    assert BY_ID["subdivision::ES-GA"].value == "Galicia"
