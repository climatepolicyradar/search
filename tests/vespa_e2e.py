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
from vespa.io import VespaQueryResponse

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


_RULEBASE_SOURCE = {None: "documents", "passages": "passages", "labels": "labels"}


def _trace_messages(node: dict | list) -> Generator[str, None, None]:
    if isinstance(node, dict):
        message = node.get("message")
        if isinstance(message, str):
            yield message
        for child in node.get("children", []):
            yield from _trace_messages(child)
    elif isinstance(node, list):
        for child in node:
            yield from _trace_messages(child)


def get_rule_rewrite(vespa_app: Vespa, query: str, rulebase: str | None) -> str:
    """
    The query as the semantic rule engine leaves it, for `query` under `rulebase`.

    Reads the `SemanticSearcher: Rewrote query: [...]` trace line, which is the
    rule engine's own output before any later stage (stemming, lowercasing,
    grouping) touches the query - so it reflects rule changes only, not noise
    from those later stages. Falls back to the pre-rule-engine parsed query when
    no rule matched, so "no rewrite happened" is still a stable, comparable value.
    """
    source = _RULEBASE_SOURCE[rulebase]
    body: dict[str, object] = {
        "yql": f"select * from sources {source} where userQuery()",
        "query": query,
        "hits": 0,
        "timeout": "5s",
        "model.language": "en",
        "tracelevel": 4,
    }
    if rulebase is not None:
        body["rules.rulebase"] = rulebase

    response = vespa_app.query(body=body)
    assert isinstance(response, VespaQueryResponse)
    messages = list(_trace_messages(response.json.get("trace", {})))

    for message in messages:
        prefix = "SemanticSearcher: Rewrote query: ["
        if message.startswith(prefix):
            return message[len(prefix) : -1]

    for message in messages:
        prefix = "Query parsed to: "
        if message.startswith(prefix):
            return message[len(prefix) :]

    raise AssertionError(f"no parsed-query trace line found for query={query!r}")
