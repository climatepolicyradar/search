"""
Validate a real feed operation end to end: contract -> Vespa -> REST API.

Throwaway: drop a documents feed op (one line of a
``documents_feed_materializer.jsonl``) into ``tests/fixtures/`` and run
``uv run pytest tests/test_validate_document_e2e.py``.
"""

from http import HTTPStatus
from typing import Any
from unittest.mock import patch

import pytest
import requests as req
from fastapi.testclient import TestClient
from vespa.application import Vespa

from tests.test_validate_document import _doc_id, feed_op  # noqa: F401
from tests.vespa_e2e import _TEST_SETTINGS

pytest_plugins = ["tests.vespa_e2e"]


def test_feed_op_is_accepted_and_served_by_the_api(
    vespa_app: Vespa, feed_op: dict[str, Any], monkeypatch: pytest.MonkeyPatch
):
    doc_id = _doc_id(feed_op)
    r = req.put(
        f"{vespa_app.end_point}/document/v1/documents/documents/docid/{doc_id}",
        json={"fields": feed_op["fields"], "create": True},
        timeout=10,
    )
    assert r.status_code == HTTPStatus.OK, r.text

    # `api.routers` resolves settings at import time.
    monkeypatch.setenv("VESPA_ENDPOINT", str(_TEST_SETTINGS.vespa_endpoint))
    monkeypatch.setenv("VESPA_READ_TOKEN", "")
    from api.main import app

    with patch("api.routers.settings", _TEST_SETTINGS):
        client = TestClient(app)

        r = client.get(f"/search/documents/{doc_id}")
        assert r.status_code == HTTPStatus.OK, r.text
        assert r.json()["data"]["id"] == doc_id

        title = feed_op["fields"]["title"]["assign"]
        r = client.get("/search/documents", params={"query": title})
        assert r.status_code == HTTPStatus.OK, r.text
        assert doc_id in [d["id"] for d in r.json()["results"]], r.text
