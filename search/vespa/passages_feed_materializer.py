import gzip
from pathlib import Path
from typing import NotRequired, TypedDict

import boto3
import orjson

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import SourceDocument
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.embeddings_input_v2 import TextBlock
from search.vespa.sources.embeddings_input_v2 import read as read_embeddings_input_v2

# Paths
REPO_ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_CACHE_DIR = REPO_ROOT_DIR / ".data_cache" / "vespa"
OUTPUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class VespaPassage(TypedDict):
    id: str
    idx: int
    language: str
    text: str
    document_id: str


class VespaPassageUpdate(TypedDict):
    id: VespaAssign[str]
    idx: VespaAssign[int]
    language: VespaAssign[str]
    text: VespaAssign[str]
    document_id: VespaAssign[str]
    document_ref: VespaAssign[str]
    principal_document_ref: NotRequired[VespaAssign[str]]
    heading_id: NotRequired[VespaAssign[str]]


BATCH_SIZE = 10_000


def _is_principal(document: SourceDocument) -> bool:
    return any(
        label["value"]["id"] == "status::Principal"
        for label in (document.get("labels") or [])
    )


def _derive_principal_id(document: SourceDocument) -> str | None:
    """Return the id of this document's Principal, or None if it has none."""
    if _is_principal(document):
        return document["id"]
    for rel in document.get("documents") or []:
        if rel.get("type") in {"member_of", "is_version_of"}:
            return rel["value"]["id"]
    return None


def _build_principal_id_lookup() -> dict[str, str]:
    """Build a `{document_id → principal_id}` map for the current dataset."""
    lookup: dict[str, str] = {}
    for doc in read_documents():
        principal_id = _derive_principal_id(doc)
        if principal_id is not None:
            lookup[doc["id"]] = principal_id
    return lookup


def _text_block_to_vespa_update(
    block: TextBlock,
    document_id: str,
    principal_id: str | None = None,
) -> VespaUpdate[VespaPassageUpdate]:
    """
    Build the Vespa update for a single passage/text block.

    `document_ref` is set to the full Vespa document id of the parent document
    so imported doc-level fields (principal_id, geographies, ...) resolve at
    query time. `principal_document_ref` is set when the parent document has
    a derivable Principal, so Principal-scoped imports (principal_title, ...)
    resolve too.
    """
    fields: VespaPassageUpdate = {
        "id": {"assign": block["id"]},
        "idx": {"assign": block["idx"]},
        "language": {"assign": block["language"]},
        "text": {"assign": block["text"]},
        "document_id": {"assign": document_id},
        "document_ref": {"assign": f"id:documents:documents::{document_id}"},
    }

    if principal_id is not None:
        fields["principal_document_ref"] = {
            "assign": f"id:documents:documents::{principal_id}"
        }

    heading_id = block.get("heading_id")
    if heading_id is not None:
        fields["heading_id"] = {"assign": heading_id}

    return {
        "update": f"id:passages:passages::{block['id']}",
        "create": True,
        "fields": fields,
    }


def passages_feed_materializer():
    total = 0
    batch: list[bytes] = []

    principal_id_lookup = _build_principal_id_lookup()
    print(f"Built principal_id lookup for {len(principal_id_lookup)} documents.")

    output_file = OUTPUT_CACHE_DIR / "passages_feed_materializer.jsonl"
    output_file_gz = OUTPUT_CACHE_DIR / "passages_feed_materializer.jsonl.gz"
    with output_file.open("wb") as f, gzip.open(output_file_gz, "wb") as f_gz:
        for document_id, inference_result in read_embeddings_input_v2():
            pdf_data = inference_result.get("pdf_data")
            text_blocks = pdf_data.get("text_blocks") if pdf_data is not None else None
            if text_blocks is None:
                continue

            principal_id = principal_id_lookup.get(document_id)
            for block in text_blocks:
                vespa_update = _text_block_to_vespa_update(
                    block, document_id, principal_id=principal_id
                )
                batch.append(orjson.dumps(vespa_update) + b"\n")

                if len(batch) >= BATCH_SIZE:
                    f.writelines(batch)
                    f_gz.writelines(batch)
                    total += len(batch)
                    batch = []

        if batch:
            f.writelines(batch)
            f_gz.writelines(batch)
            total += len(batch)

    s3 = boto3.client("s3")
    s3.upload_file(
        str(output_file),
        "cpr-cache",
        "search/vespa/passages_feed_materializer.jsonl",
    )
    s3.upload_file(
        str(output_file_gz),
        "cpr-cache",
        "search/vespa/passages_feed_materializer.jsonl.gz",
    )
    print(f"Uploaded {total} passages to S3.")


if __name__ == "__main__":
    passages_feed_materializer()
