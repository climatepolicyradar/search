from datetime import datetime
from typing import TypedDict, cast

import orjson

from search.data_in_models import Document

"""
We use TypedDicts over Pydantic models here
for performance when running through large data sets.
We use the Pydantic models for tests
and probably would in liver systems for parsing at the edge.
"""


class VespaLabelField(TypedDict):
    id: str
    type: str
    value: str
    timestamp: int | None
    relationship: str


class VespaAssignOp(TypedDict):
    assign: str | None


class VespaAssignLabelsOp(TypedDict):
    assign: list[VespaLabelField]


class VespaAssignStrOp(TypedDict):
    assign: str


class VespaAssignMapOp[T](TypedDict):
    assign: dict[str, T]


class VespaUpdateFields(TypedDict, total=False):
    title: VespaAssignOp
    description: VespaAssignOp
    labels: VespaAssignLabelsOp
    document_source: VespaAssignStrOp
    attributes_string: VespaAssignMapOp[str]
    attributes_double: VespaAssignMapOp[float]
    attributes_boolean: VespaAssignMapOp[int]


# These models are replicas of the Pydantic data models
class SourceLabel(TypedDict):
    id: str
    type: str
    value: str


class SourceLabelRelationship(TypedDict):
    type: str
    value: SourceLabel
    timestamp: str | None


class SourceDocument(TypedDict, total=False):
    id: str
    title: str
    description: str
    labels: list[SourceLabelRelationship]
    attributes: dict[str, str | float | bool]


class VespaUpdate(TypedDict, total=False):
    update: str
    create: bool
    fields: VespaUpdateFields


def _to_unix_timestamp(ts_str: str | None) -> int | None:
    """Safely convert ISO string to int, returns None if invalid/missing."""
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str).timestamp())
    except (ValueError, TypeError):
        return None


def typeddict_document_to_vespa_update(
    document: SourceDocument,
) -> VespaUpdate:
    """To be used in systems where using Pydantic models would hinder performance. Otherwise prefer document_to_vespa_update."""

    attrs = document.get("attributes") or {}
    fields: VespaUpdateFields = {
        "title": {"assign": document.get("title")},
        "description": {"assign": document.get("description")},
        "labels": {
            "assign": [
                {
                    "id": label["value"]["id"],
                    "type": label["value"]["type"],
                    "value": label["value"]["value"],
                    "timestamp": _to_unix_timestamp(label.get("timestamp")),
                    "relationship": label.get("type", "related"),
                }
                for label in (document.get("labels") or [])
            ]
        },
        "document_source": {"assign": orjson.dumps(document).decode()},
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
    }
    return {
        "update": f"id:documents:documents::{document.get('id')}",
        "create": True,
        "fields": fields,
    }


def document_to_vespa_update(document: Document) -> VespaUpdate:
    return typeddict_document_to_vespa_update(
        # We know these types are identical, so cast is __OK__ here.
        # We could use something like PydanType, but it feels like overkill for
        # a piece of the system that is non-production.
        # @see: https://github.com/unclecode/pydantype
        cast(SourceDocument, document.model_dump())
    )
