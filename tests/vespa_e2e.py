import datetime
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import NotRequired, TypedDict

import httpx2
import pytest
import requests as req
from cpr_contracts import Document
from vespa.application import Vespa
from vespa.deployment import VespaDocker

from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    Filter,
    Settings,
)
from search.vespa.models import VespaAssign, VespaUpdate

logger = logging.getLogger(__name__)

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



async def get_search_ids(httpx_client: httpx2.AsyncClient, filter_: Filter) -> set[str]:
    engine = DevVespaDocumentSearchEngine(settings=_TEST_SETTINGS, httpx=httpx_client)
    docs = await engine.asearch(
        query=None,
        pagination=Pagination(page_token=1, page_size=10),
        order_by=[OrderBy(field="relevance", direction="desc")],
        filters=filter_,
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


# Builds the Vespa update the e2e tests feed for a test `Document`. It no longer feeds
# production (the Fusion export does), but the API still reads `document_source`
# back out of Vespa, so the tests need to write it.
class VespaLabelField(TypedDict):
    id: str
    type: str
    value: str
    timestamp: int | None
    relationship: str | None
    # 👇 do not rely on these, they are experimental
    count: int | None
    passages_id: str | None


class VespaDocument(TypedDict):
    title: VespaAssign[str]
    description: VespaAssign[str | None]
    labels: VespaAssign[list[VespaLabelField]]
    geographies: VespaAssign[list[str]]
    document_source: VespaAssign[str]
    attributes_string: VespaAssign[dict[str, str]]
    attributes_double: VespaAssign[dict[str, float]]
    attributes_boolean: VespaAssign[dict[str, int]]
    attributes_identifiers: VespaAssign[dict[str, str]]
    attributes_published_date: NotRequired[VespaAssign[int]]
    attributes_created_at: NotRequired[VespaAssign[int]]
    principal_id: NotRequired[VespaAssign[str]]


def _strip_control_chars(s: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s) if s else s


def _to_unix_timestamp(ts: str | datetime.datetime | None) -> int | None:
    """Safely convert ISO string or datetime to Unix timestamp, returns None if invalid/missing."""
    if not ts:
        return None
    if isinstance(ts, datetime.datetime):
        return int(ts.timestamp())
    try:
        normalised = ts.replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(normalised).timestamp())
    except (ValueError, TypeError):
        return None


def _published_timestamp_from_attributes(
    attributes: dict[str, str | float | bool] | None,
) -> int | None:
    """
    Derive a Unix timestamp for sort from `published_date` when present.

    :param attributes: Document attributes from the data-in payload
    :type attributes: dict[str, str | float | bool] | None
    :return: Epoch seconds or ``None`` when not sortable
    :rtype: int | None
    """
    if not attributes:
        return None
    raw = attributes.get("published_date")
    if isinstance(raw, str):
        return _to_unix_timestamp(raw)
    return None


def _created_timestamp_from_attributes(
    attributes: dict[str, str | float | bool] | None,
) -> int | None:
    """
    Derive a Unix timestamp for sort from `created` (the RDS row timestamp).

    `created` arrives without a timezone and is UTC, so a naive value is read
    as UTC rather than local time.

    :param attributes: Document attributes from the data-in payload
    :type attributes: dict[str, str | float | bool] | None
    :return: Epoch seconds or ``None`` when not sortable
    :rtype: int | None
    """
    raw = (attributes or {}).get("created")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        created = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=datetime.UTC)
    return int(created.timestamp())


def _derive_principal_id(document: Document) -> str | None:
    """Return the id of this document's Principal, or None if there is none."""

    # A document with a `status::Principal` label is itself a Principal.
    # Its principal_id is its own id - self-referential, so it appears in its own grouping bucket.
    is_principal = any(
        label.value.id == "status::Principal"
        for label in document.labels
    )
    if is_principal:
        return document.id

    # Otherwise, the first `member_of` / `is_version_of` relationship target is the parent Principal.
    matches = [
        rel
        for rel in document.documents
        if rel.type in {"member_of", "is_version_of"}
    ]

    if not matches:
        return None

    # If multiple candidates exist, take the first and log a warning.
    if len(matches) > 1:
        logger.warning(
            f"document {document.id} has multiple principal-candidate relationships - using the first."
        )

    return matches[0].value.id


def _source_document_to_vespa_update(
    document: Document,
) -> VespaUpdate[VespaDocument]:
    attrs = document.attributes or {}
    title_clean = _strip_control_chars(document.title)
    published_ts = _published_timestamp_from_attributes(attrs)
    created_ts = _created_timestamp_from_attributes(attrs)
    principal_id = _derive_principal_id(document)
    fields: VespaDocument = {
        "title": {"assign": title_clean},
        "description": {
            "assign": _strip_control_chars(document.description or "")
            if document.description
            else None
        },
        "labels": {
            "assign": [
                {
                    "id": label.value.id,
                    "type": label.value.type,
                    "value": label.value.value,
                    "timestamp": _to_unix_timestamp(label.timestamp),
                    "relationship": label.type,
                    "count": None,
                    "passages_id": None,
                }
                for label in (document.labels or [])
            ]
        },
        "geographies": {
            "assign": [
                label.value.value
                for label in (document.labels or [])
                if label.type == "geography"
            ]
        },
        "document_source": {"assign": document.model_dump_json()},
        "attributes_string": {
            "assign": {k: str(v) for k, v in attrs.items() if isinstance(v, str)}
        },
        "attributes_double": {
            "assign": {
                k: float(v)
                for k, v in attrs.items()
                if isinstance(v, (int, float))
                # this is needed because
                # >>> isinstance(True, int)
                # True
                # >>> isinstance(False, int)
                # True
                and not isinstance(v, bool)
            }
        },
        "attributes_boolean": {
            "assign": {k: int(v) for k, v in attrs.items() if isinstance(v, bool)}
        },
        "attributes_identifiers": {
            "assign": {
                # we do not mind if this is duplicated in attributes_string
                # as it is used for boosting
                k.replace("identifier::", ""): str(v)
                for k, v in attrs.items()
                if k.startswith("identifier::")
            }
        },
    }
    if published_ts is not None:
        fields["attributes_published_date"] = {"assign": published_ts}

    if created_ts is not None:
        fields["attributes_created_at"] = {"assign": created_ts}

    if principal_id is not None:
        fields["principal_id"] = {"assign": principal_id}

    vespa_update: VespaUpdate[VespaDocument] = {
        "update": f"id:documents:documents::{document.id}",
        "create": True,
        "fields": fields,
    }
    return vespa_update

