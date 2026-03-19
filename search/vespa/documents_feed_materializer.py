import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import boto3
import orjson

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import SourceDocument
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.inference_results import read as read_inference_results

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_CACHE_DIR = REPO_ROOT_DIR / ".data_cache" / "vespa"
OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
    description_index: VespaAssign[str | None]
    labels: VespaAssign[list[VespaLabelField]]
    geographies: VespaAssign[list[str]]
    document_source: VespaAssign[str]
    attributes_string: VespaAssign[dict[str, str]]
    attributes_double: VespaAssign[dict[str, float]]
    attributes_boolean: VespaAssign[dict[str, int]]


def _strip_control_chars(s: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s) if s else s


def _to_unix_timestamp(ts_str: str | None) -> int | None:
    """Safely convert ISO string to int, returns None if invalid/missing."""
    if not ts_str:
        return None
    try:
        return int(datetime.fromisoformat(ts_str).timestamp())
    except (ValueError, TypeError):
        return None


def _build_family_description_map(documents: list[SourceDocument]) -> dict[str, str]:
    child_to_family_desc: dict[str, str] = {}
    for doc in documents:
        family_desc = _strip_control_chars(doc.get("description") or "")
        if not family_desc:
            continue
        for rel in doc.get("documents") or []:
            if rel.get("type") not in ("has_version", "has_member"):
                continue
            child_id = (rel.get("value") or {}).get("id")
            if child_id:
                child_to_family_desc[child_id] = family_desc
    return child_to_family_desc


def documents_feed_materializer():
    documents = list(read_documents())
    family_desc_map = _build_family_description_map(documents)
    length = 0

    output_file = OUTPUT_CACHE_DIR / "documents_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for document in documents:
            attrs = document.get("attributes") or {}
            vespa_update: VespaUpdate[VespaDocument] = {
                "update": f"id:documents:documents::{document.get('id')}",
                "create": True,
                "fields": {
                    "title": {"assign": _strip_control_chars(document["title"])},
                    "description": {
                        "assign": _strip_control_chars(
                            document.get("description") or ""
                        )
                        if document.get("description")
                        else None
                    },
                    "description_index": {
                        "assign": (
                            _strip_control_chars(document.get("description") or "")
                            or family_desc_map.get(document["id"], "")
                        )
                        or None
                    },
                    "labels": {
                        "assign": [
                            {
                                "id": label["value"]["id"],
                                "type": label["value"]["type"],
                                "value": label["value"]["value"],
                                "timestamp": _to_unix_timestamp(label.get("timestamp")),
                                "relationship": label.get("type", "related"),
                                "count": None,
                                "passages_id": None,
                            }
                            for label in (document.get("labels") or [])
                        ]
                    },
                    "geographies": {
                        "assign": [
                            label["value"]["value"]
                            for label in (document.get("labels") or [])
                            if label.get("type") == "geography"
                        ]
                    },
                    "document_source": {"assign": orjson.dumps(document).decode()},
                    "attributes_string": {
                        "assign": {
                            k: str(v) for k, v in attrs.items() if isinstance(v, str)
                        }
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
                        "assign": {
                            k: int(v) for k, v in attrs.items() if isinstance(v, bool)
                        }
                    },
                },
            }
            f.write(orjson.dumps(vespa_update) + b"\n")
            length += 1

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/documents_feed_materializer.jsonl",
    )
    print(f"Uploaded {length} documents to S3.")


class VespaDocumentConcepts(TypedDict):
    concepts: VespaAssign[list[VespaLabelField]]


def documents_concepts_feed_materializer():
    inference_results_input = read_inference_results()
    length = 0

    output_file = OUTPUT_CACHE_DIR / "documents_concepts_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for document_id, inference_result_input in inference_results_input:
            concept_counts: Counter[str] = Counter()
            concept_names: dict[str, str] = {}
            concept_passages: dict[str, list[str]] = {}

            for passage_id, inference_results in inference_result_input.items():
                for inference_result in inference_results:
                    concept_id = inference_result["id"]
                    concept_counts[concept_id] += 1
                    concept_names[concept_id] = inference_result["name"]
                    concept_passages.setdefault(concept_id, []).append(passage_id)

            vespa_concepts: list[VespaLabelField] = [
                {
                    "id": concept_id,
                    "type": "concept",
                    "value": concept_names[concept_id],
                    "count": count,
                    "passages_id": "::".join(concept_passages[concept_id]),
                    "relationship": None,
                    "timestamp": None,
                }
                for concept_id, count in concept_counts.items()
            ]

            update_op: VespaUpdate[VespaDocumentConcepts] = {
                "update": f"id:documents:documents::{document_id}",
                "fields": {
                    "concepts": {"assign": vespa_concepts},
                },
                "create": False,
            }
            f.write(orjson.dumps(update_op) + b"\n")
            length += 1

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/documents_concepts_feed_materializer.jsonl",
    )
    print(f"Uploaded {length} documents to S3.")


if __name__ == "__main__":
    documents_feed_materializer()
