import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import requests as req
from vespa.application import Vespa
from vespa.deployment import VespaDocker

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    Filter,
    Settings,
)
from search.vespa.documents_feed_materializer import _source_document_to_vespa_update
from search.vespa.sources.data_in_api import (
    SourceDocument,
)

VESPA_APP_DIR = Path(__file__).resolve().parents[1] / "vespa" / "app"
# we try not to use 8080 as this _might_ be the currently running local server
_PORT = 8089
_TEST_SETTINGS = Settings(
    vespa_endpoint=f"http://localhost:{_PORT}",  # type: ignore[arg-type]
    vespa_read_token="",  # nosec B106
)


def _vespa_ready() -> bool:
    try:
        return (
            req.get(
                f"{_TEST_SETTINGS.vespa_endpoint}state/v1/health", timeout=2
            ).status_code
            == req.codes.ok
        )
    except Exception:
        return False


@pytest.fixture(scope="module")
def vespa_app() -> Generator[Vespa, None, None]:
    remove_container = bool(os.environ.get("TEST_VESPA_REMOVE_CONTAINER"))
    vespa_docker = None
    app_dir = None

    if _vespa_ready():
        app = Vespa(url="http://localhost", port=_PORT)
    else:
        app_dir = Path(tempfile.mkdtemp())
        shutil.copytree(VESPA_APP_DIR / "schemas", app_dir / "schemas")
        shutil.copytree(
            VESPA_APP_DIR / "lucene-linguistics", app_dir / "lucene-linguistics"
        )
        shutil.copytree(VESPA_APP_DIR / "rules", app_dir / "rules")
        shutil.copy(
            Path(__file__).parent / "vespa_test_services.xml", app_dir / "services.xml"
        )
        vespa_docker = VespaDocker(port=_PORT)
        app = vespa_docker.deploy_from_disk(
            application_name="searchtestvespae2e",
            application_root=app_dir,
            max_wait_application=600,
        )

    try:
        yield app
    finally:
        if remove_container and vespa_docker and vespa_docker.container:
            vespa_docker.container.remove(force=True)
        if app_dir is not None:
            shutil.rmtree(app_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_docs(vespa_app: Vespa):
    """Delete all documents after each test for isolation."""
    yield
    vespa_app.delete_all_docs(
        content_cluster_name="search-production", schema="documents"
    )


def _feed_document(app: Vespa, document: SourceDocument) -> None:
    """Feed a document as an update operation — same format as JSONL feed."""
    op = _source_document_to_vespa_update(document)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document['id']}",
        json={**op, "create": True},
        timeout=5,
    )
    r.raise_for_status()


def _feed_document_without_title(app: Vespa, document: SourceDocument) -> None:
    """
    Feed a document update with ``title`` intentionally omitted.

    This creates a true missing ``title_sort`` value in Vespa so we can verify
    missing-title sort behaviour end-to-end.
    """
    op = _source_document_to_vespa_update(document)
    fields = dict(op.get("fields", {}))
    fields.pop("title", None)
    r = req.put(
        f"{app.end_point}/document/v1/documents/documents/docid/{document['id']}",
        json={**op, "fields": fields, "create": True},
        timeout=5,
    )
    r.raise_for_status()


def _ids(filter_: Filter) -> set[str]:
    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    docs = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters_json_string=filter_.model_dump_json(),
    )
    return {doc.id for doc in docs.results}
