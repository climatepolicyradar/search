import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import NotRequired, TypedDict

import boto3
import orjson

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import SourceDocument
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.embeddings_input_v2 import read as read_embeddings_input_v2
from search.vespa.sources.inference_results import read as read_inference_results

logger = logging.getLogger(__name__)

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


def _to_unix_timestamp(ts_str: str | None) -> int | None:
    """Safely convert ISO string to int, returns None if invalid/missing."""
    if not ts_str:
        return None
    try:
        normalised = ts_str.replace("Z", "+00:00")
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


def _derive_principal_id(document: SourceDocument) -> str | None:
    """Return the id of this document's Principal, or None if there is none."""

    # A document with a `status::Principal` label is itself a Principal.
    # Its principal_id is its own id - self-referential, so it appears in its own grouping bucket.
    is_principal = any(
        label["value"]["id"] == "status::Principal"
        for label in (document.get("labels") or [])
    )
    if is_principal:
        return document["id"]

    # Otherwise, the first `member_of` / `is_version_of` relationship target is the parent Principal.
    matches = [
        rel
        for rel in (document.get("documents") or [])
        if rel.get("type") in {"member_of", "is_version_of"}
    ]

    if not matches:
        return None

    # If multiple candidates exist, take the first and log a warning.
    if len(matches) > 1:
        logger.warning(
            f"document {document['id']} has multiple principal-candidate relationships - using the first."
        )

    return matches[0]["value"]["id"]


def _source_document_to_vespa_update(
    document: SourceDocument,
) -> VespaUpdate[VespaDocument]:
    attrs = document.get("attributes") or {}
    title_clean = _strip_control_chars(document["title"])
    published_ts = _published_timestamp_from_attributes(attrs)
    principal_id = _derive_principal_id(document)
    fields: VespaDocument = {
        "title": {"assign": title_clean},
        "description": {
            "assign": _strip_control_chars(document.get("description") or "")
            if document.get("description")
            else None
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
        "update": f"id:documents:documents::{document.get('id')}",
        "create": True,
        "fields": fields,
    }
    return vespa_update


def documents_feed_materializer():
    documents = read_documents()
    length = 0

    output_file = OUTPUT_CACHE_DIR / "documents_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for document in documents:
            vespa_update = _source_document_to_vespa_update(document)
            f.write(orjson.dumps(vespa_update) + b"\n")
            length += 1

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/documents_feed_materializer.jsonl",
    )
    print(f"Uploaded {length} documents to S3.")


class VespaDocumentPassage(TypedDict):
    text_block_id: str
    language: str
    type: str
    type_confidence: float
    page_number: int
    text: str
    heading_id: NotRequired[str | None]


class VespaDocumentPassages(TypedDict):
    passages: VespaAssign[list[VespaDocumentPassage]]


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
                    "id": f"concept::{concept_id}",
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


def documents_passages_feed_materializer():
    length = 0

    output_file = OUTPUT_CACHE_DIR / "documents_passages_feed_materializer.jsonl"
    with output_file.open("wb") as f:
        for document_id, inference_result in read_embeddings_input_v2():
            pdf_data = inference_result.get("pdf_data")
            text_blocks = pdf_data.get("text_blocks") if pdf_data is not None else None
            if not text_blocks:
                continue

            passages: list[VespaDocumentPassage] = [
                {
                    "text_block_id": block["id"],
                    "language": block["language"],
                    "type": block["type"],
                    "type_confidence": block["type_confidence"],
                    "page_number": block["pages"][0]["number"]
                    if block.get("pages")
                    else 0,
                    "text": block["text"],
                    "heading_id": block.get("heading_id"),
                }
                for block in text_blocks
            ]

            update_op: VespaUpdate[VespaDocumentPassages] = {
                "update": f"id:documents:documents::{document_id}",
                "fields": {"passages": {"assign": passages}},
                "create": False,
            }
            f.write(orjson.dumps(update_op) + b"\n")
            length += 1

    boto3.client("s3").upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/documents_passages_feed_materializer.jsonl",
    )
    print(f"Uploaded {length} document passage updates to S3.")


if __name__ == "__main__":
    documents_feed_materializer()
