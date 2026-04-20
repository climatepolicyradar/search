import pytest

from search.engines.dev_vespa import DevVespaDocumentSearchEngine


@pytest.mark.parametrize(
    "s, expected",
    [
        (
            "geography::geography::USA::United States of America",
            ("geography", "geography::USA", "United States of America"),
        ),
        (
            "geography::geography::USA_west::United States of America",
            ("geography", "geography::USA_west", "United States of America"),
        ),
    ],
)
def test_parse_label_type_id_value(s, expected):
    assert DevVespaDocumentSearchEngine.parse_label_type_id_value(s) == expected
