import gzip
from pathlib import Path
from typing import NotRequired, TypedDict

import boto3
import orjson
from cpr_contracts import Document
from mypy_boto3_s3 import S3Client

from search.vespa.models import VespaAssign, VespaUpdate
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

# Bounds each `vespa feed` subprocess to a single chunk so a connection drop late
# in a run only costs that chunk's records, not a multi-hour single-file feed.
CHUNK_SIZE = 200_000


def _is_principal(document: Document) -> bool:
    return any(
        label.value.id == "status::Principal"
        for label in (document.labels or [])
    )


def _derive_principal_id(document: Document) -> str | None:
    """Return the id of this document's Principal, or None if it has none."""
    if _is_principal(document):
        return document.id
    for rel in document.documents or []:
        if rel.type in {"member_of", "is_version_of"}:
            return rel.value.id
    return None


def _build_principal_id_lookup() -> dict[str, str]:
    """Build a `{document_id → principal_id}` map for the current dataset."""
    lookup: dict[str, str] = {}
    for doc in read_documents():
        principal_id = _derive_principal_id(doc)
        if principal_id is not None:
            lookup[doc.id] = principal_id
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


def _open_chunk(chunk_index: int) -> tuple[Path, Path]:
    output_file = OUTPUT_CACHE_DIR / f"passages_feed_materializer_{chunk_index}.jsonl"
    output_file_gz = OUTPUT_CACHE_DIR / f"passages_feed_materializer_{chunk_index}.jsonl.gz"
    return output_file, output_file_gz


def _upload_chunk(s3: S3Client, output_file: Path, output_file_gz: Path) -> None:
    # Kept in separate prefixes: the vespa-feeder reads every object under
    # search/vespa/passages_feed_materializer/ as a JSONL feed file, so the
    # gzip backups must live elsewhere to avoid being fed to Vespa.
    s3.upload_file(
        str(output_file),
        "cpr-cache",
        f"search/vespa/passages_feed_materializer/{output_file.name}",
    )
    s3.upload_file(
        str(output_file_gz),
        "cpr-cache",
        f"search/vespa/passages_feed_materializer_gz/{output_file_gz.name}",
    )


def passages_feed_materializer():
    total = 0
    chunk_total = 0
    chunk_index = 0
    chunks_uploaded = 0
    batch: list[bytes] = []

    principal_id_lookup = _build_principal_id_lookup()
    print(f"Built principal_id lookup for {len(principal_id_lookup)} documents.")

    s3 = boto3.client("s3")
    output_file, output_file_gz = _open_chunk(chunk_index)
    f = output_file.open("wb")
    f_gz = gzip.open(output_file_gz, "wb")

    def flush_batch() -> None:
        nonlocal batch, total, chunk_total
        f.writelines(batch)
        f_gz.writelines(batch)
        total += len(batch)
        chunk_total += len(batch)
        batch = []

    def rotate_chunk() -> None:
        nonlocal chunk_index, chunk_total, chunks_uploaded, output_file, output_file_gz, f, f_gz
        f.close()
        f_gz.close()
        _upload_chunk(s3, output_file, output_file_gz)
        chunks_uploaded += 1
        chunk_index += 1
        chunk_total = 0
        output_file, output_file_gz = _open_chunk(chunk_index)
        f = output_file.open("wb")
        f_gz = gzip.open(output_file_gz, "wb")

    try:
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
                    flush_batch()
                    if chunk_total >= CHUNK_SIZE:
                        rotate_chunk()

        if batch:
            flush_batch()
    finally:
        f.close()
        f_gz.close()

    if chunk_total > 0:
        _upload_chunk(s3, output_file, output_file_gz)
        chunks_uploaded += 1
    else:
        # Last chunk ended up empty because the final flush landed exactly on
        # a chunk boundary - nothing new to upload, clean up the empty files.
        output_file.unlink(missing_ok=True)
        output_file_gz.unlink(missing_ok=True)

    print(f"Uploaded {total} passages to S3 across {chunks_uploaded} chunk(s).")


if __name__ == "__main__":
    passages_feed_materializer()
