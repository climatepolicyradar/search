import datetime
import os
import re
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


def _validation_overrides() -> str:
    """
    Blanket schema-change allowance for the throwaway e2e application.

    The fixture reuses an already-running container when it finds one, so a
    schema change that alters indexing (e.g. a new linguistics profile on
    `title`) is rejected against the previously deployed app unless it is
    allowed here.
    """
    until = datetime.date.today() + datetime.timedelta(days=25)
    return (
        "<validation-overrides>\n"
        f'    <allow until="{until.isoformat()}">indexing-change</allow>\n'
        f'    <allow until="{until.isoformat()}">field-type-change</allow>\n'
        "</validation-overrides>\n"
    )


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
        (app_dir / "validation-overrides.xml").write_text(_validation_overrides())
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



def get_search_ids(filter_: Filter) -> set[str]:
    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS)
    docs = engine.search(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters_json_string=filter_.model_dump_json(),
    )
    return {doc.id for doc in docs.results}


def first_production_text(rhs: str) -> str:
    """
    Literal text for an RHS production list's first alternative.

    Enough to feed as content that a rewritten query should match on at
    least one alternative - doesn't need to reproduce the full production
    list, quoted phrase or bare word alike.
    """
    quoted = re.match(r'\s*[?=+$-]?"([^"]*)"', rhs)
    if quoted:
        return quoted.group(1)
    bare = re.match(r"\s*[?=+$-]?(\S+)", rhs)
    return bare.group(1) if bare else rhs.strip()


def rule_cases(*filenames: str) -> list[tuple[str, str, str]]:
    """
    Derive (case_id, query, rewrite_text) from every rule across the given .sr files.

    Reads the actual files under `vespa/app/rules/` so a new rule is covered
    automatically.
    """
    cases: dict[str, str] = {}
    for filename in filenames:
        path = VESPA_APP_DIR / "rules" / filename
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("@"):
                continue
            match = re.match(r"(?P<lhs>.*?)(?:->|\+>)(?P<rhs>.*);\s*$", stripped)
            if match is None:
                continue
            lhs = match["lhs"].strip()
            cases.setdefault(lhs, first_production_text(match["rhs"]))

    return [
        (re.sub(r"[^a-z0-9]+", "-", lhs.lower()).strip("-"), lhs, rewrite_text)
        for lhs, rewrite_text in sorted(cases.items())
    ]
