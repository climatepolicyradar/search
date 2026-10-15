import logging
import re
from datetime import datetime
from typing import NotRequired, TypedDict

from cpr_contracts import Document

from search.vespa.models import VespaAssign, VespaUpdate

logger = logging.getLogger(__name__)


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
    principal_id: NotRequired[VespaAssign[str]]


def _strip_control_chars(s: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s) if s else s


def _to_unix_timestamp(ts: str | datetime | None) -> int | None:
    """Safely convert ISO string or datetime to Unix timestamp, returns None if invalid/missing."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return int(ts.timestamp())
    try:
        normalised = ts.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalised).timestamp())
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

    if principal_id is not None:
        fields["principal_id"] = {"assign": principal_id}

    vespa_update: VespaUpdate[VespaDocument] = {
        "update": f"id:documents:documents::{document.id}",
        "create": True,
        "fields": fields,
    }
    return vespa_update

