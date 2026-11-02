from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import UNMATCHED_ROUTE_LABEL, app

# A raw path here is a billing incident. `http.route` is
# the label Grafana expects to be bound, so one value per document ID (or per
# scanner probe) multiplies out across the histogram buckets. 
# @see https://app.notion.com/p/climatepolicyradar/Grafana-metrics-cardinality-spike-findings-and-actions-40c9109609a4813c9a92d2aaf57968a2?source=copy_link
DOCUMENT_ROUTE = "/search/documents/{document_id}"

SCANNER_PROBES = ["/%2eenv", "/+CSCOE+/logon.html", "/elasticsearch/.env"]


def record_labels(paths: list[str]) -> list[str]:
    """Return the `http.route` label recorded for each requested path."""
    labels: list[str] = []
    with patch(
        "api.main.search_metrics.record_success",
        side_effect=lambda **kwargs: labels.append(kwargs["path"]),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        for path in paths:
            client.get(path)
    return labels


@pytest.mark.parametrize(
    "document_id", ["AF.document.003MTMWR.n0000", "CCLW.executive.9999.1"]
)
def test_document_requests_are_labelled_with_the_route_template(document_id):
    """Each document ID collapses onto the shared route template."""
    assert record_labels([f"/search/documents/{document_id}"]) == [DOCUMENT_ROUTE]


def test_unmatched_requests_share_one_label():
    """Unrouted probes collapse into one series however many paths they try."""
    assert record_labels(SCANNER_PROBES) == [UNMATCHED_ROUTE_LABEL] * len(
        SCANNER_PROBES
    )


def test_distinct_paths_do_not_multiply_series():
    """Many distinct paths stay bounded by the number of routes they hit."""
    paths = [f"/search/documents/CCLW.executive.{index}.1" for index in range(25)]
    assert set(record_labels(paths + SCANNER_PROBES)) == {
        DOCUMENT_ROUTE,
        UNMATCHED_ROUTE_LABEL,
    }
