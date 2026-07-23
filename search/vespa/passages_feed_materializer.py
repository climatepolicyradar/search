"""
Materialize passages for the `search-vespa-feeder-passages` feed.

Output is written in two tiers:
- write buffer: an in-memory list of records, flushed to disk every
    `BATCH_SIZE` records to reduce write syscalls. Purely an I/O
    optimisation, invisible outside this module.
- chunk: an on-disk/S3 output file, rotated (closed, uploaded, reopened
    as the next one) every `CHUNK_SIZE` records. Chunk size decides how
    long a single `vespa feed` subprocess runs for downstream in the
    feeder, so a connection drop late in a feed only costs one chunk's
    records, not the whole (multi-hour, single-file) run.
"""

import gzip
import shutil
from collections import Counter
from pathlib import Path
from typing import NotRequired, TypedDict

import boto3
import orjson
from cpr_contracts import Document
from mypy_boto3_s3 import S3Client

from search.vespa.models import VespaAssign, VespaUpdate
from search.vespa.sources.data_in_api import DATA_CACHE_FILE as DOCUMENTS_CACHE
from search.vespa.sources.data_in_api import read as read_documents
from search.vespa.sources.embeddings_input_v2 import (
    DATA_CACHE_DIR as EMBEDDINGS_CACHE_DIR,
)
from search.vespa.sources.embeddings_input_v2 import TextBlock
from search.vespa.sources.embeddings_input_v2 import read as read_embeddings_input_v2
from search.vespa.sources.inference_results import (
    DATA_CACHE_DIR as INFERENCE_RESULTS_CACHE_DIR,
)
from search.vespa.sources.inference_results import read as read_inference_results

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


class VespaConceptField(TypedDict):
    id: str
    type: str
    value: str
    count: int


class VespaCoordinate(TypedDict):
    x: float
    y: float


class VespaBoundingBox(TypedDict):
    coordinates: list[VespaCoordinate]


class VespaPageBoxes(TypedDict):
    number: int
    bounding_boxes: list[VespaBoundingBox]


class VespaPassageUpdate(TypedDict):
    id: VespaAssign[str]
    idx: VespaAssign[int]
    language: VespaAssign[str]
    text: VespaAssign[str]
    document_id: VespaAssign[str]
    document_ref: VespaAssign[str]
    principal_document_ref: NotRequired[VespaAssign[str]]
    heading_id: NotRequired[VespaAssign[str]]
    heading_text: NotRequired[VespaAssign[str]]
    concepts: NotRequired[VespaAssign[list[VespaConceptField]]]
    pages: NotRequired[VespaAssign[list[int]]]
    page_bounding_boxes: NotRequired[VespaAssign[list[VespaPageBoxes]]]

BATCH_SIZE = 10_000  # write-buffer flush size
CHUNK_SIZE = 200_000  # output file rotation size, see module docstring


def _cleanup_source_cache(path: Path) -> None:
    """
    Remove a source's local cache once this flow is done reading it.

    Source caches are only ever consumed by one flow per process, so on the
    ECS runner (a fresh filesystem per run) leaving them in place just burns
    disk for the rest of the run. Safe to call even if `path` is already
    gone.
    """
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


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


def _build_passage_concepts_lookup() -> dict[str, list[VespaConceptField]]:
    """
    Build a `{passage_id → [concept, ...]}` map from the inference results.

    Concepts are aggregated per passage: repeated hits of the same concept in a
    passage collapse to a single entry whose `count` is the number of hits.
    Mirrors the aggregation in `documents_concepts_feed_materializer`, but at
    passage grain (no cross-passage accumulation).
    """
    lookup: dict[str, list[VespaConceptField]] = {}
    for _document_id, inference_result_input in read_inference_results():
        for passage_id, inference_results in inference_result_input.items():
            concept_counts: Counter[str] = Counter()
            concept_names: dict[str, str] = {}
            for inference_result in inference_results:
                concept_id = inference_result["id"]
                concept_counts[concept_id] += 1
                concept_names[concept_id] = inference_result["name"]

            lookup[passage_id] = [
                {
                    "id": f"concept::{concept_id}",
                    "type": "concept",
                    "value": concept_names[concept_id],
                    "count": count,
                }
                for concept_id, count in concept_counts.items()
            ]
    return lookup


def _text_block_to_vespa_update(
    block: TextBlock,
    document_id: str,
    principal_id: str | None = None,
    concepts: list[VespaConceptField] | None = None,
    block_text_by_id: dict[str, str] | None = None,
) -> VespaUpdate[VespaPassageUpdate]:
    """
    Build the Vespa update for a single passage/text block.

    `document_ref` is set to the full Vespa document id of the parent document
    so imported doc-level fields (principal_id, geographies, ...) resolve at
    query time. `principal_document_ref` is set when the parent document has
    a derivable Principal, so Principal-scoped imports (principal_title, ...)
    resolve too. `concepts` are the concepts detected within this passage.
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
        heading_text = (block_text_by_id or {}).get(heading_id)
        if heading_text is not None:
            fields["heading_text"] = {"assign": heading_text}

    if concepts:
        fields["concepts"] = {"assign": concepts}

    pages = [page["number"] for page in block.get("pages", [])]
    if pages:
        fields["pages"] = {"assign": pages}

    page_bounding_boxes: list[VespaPageBoxes] = [
        {
            "number": page["number"],
            "bounding_boxes": [
                {
                    "coordinates": [
                        {"x": coord["x"], "y": coord["y"]}
                        for coord in box["coordinates"]
                    ]
                }
                for box in page["bounding_boxes"]
            ],
        }
        for page in block.get("pages", [])
    ]
    if page_bounding_boxes:
        fields["page_bounding_boxes"] = {"assign": page_bounding_boxes}

    return {
        "update": f"id:passages:passages::{block['id']}",
        "create": True,
        "fields": fields,
    }


def _open_chunk(chunk_index: int) -> tuple[Path, Path]:
    """Return the local (plain, gzip) file paths for the given chunk index."""
    output_file = OUTPUT_CACHE_DIR / f"passages_feed_materializer_{chunk_index}.jsonl"
    output_file_gz = OUTPUT_CACHE_DIR / f"passages_feed_materializer_{chunk_index}.jsonl.gz"
    return output_file, output_file_gz


def _upload_chunk(s3: S3Client, output_file: Path, output_file_gz: Path) -> None:
    """
    Upload one chunk's plain and gzip files to S3.

    Kept in separate prefixes: the vespa-feeder reads every object under
    search/vespa/passages_feed_materializer/ as a JSONL feed file, so the
    gzip backups must live elsewhere to avoid being fed to Vespa.
    """
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


class _ChunkWriter:
    """
    Buffers passage lines to disk, rotating to a new S3-uploaded chunk.

    Rotates every `CHUNK_SIZE` records. See the module docstring for why
    chunking matters to the downstream feeder.
    """

    def __init__(self, s3: S3Client) -> None:
        """Open the first chunk's plain and gzip files, ready for `append`."""
        self._s3 = s3
        self.total = 0
        self.chunks_uploaded = 0
        self._chunk_index = 0
        self._chunk_total = 0
        self._write_buffer: list[bytes] = []
        self._output_file, self._output_file_gz = _open_chunk(self._chunk_index)
        self._f = self._output_file.open("wb")
        self._f_gz = gzip.open(self._output_file_gz, "wb")

    def append(self, line: bytes) -> None:
        """
        Buffer one JSONL line, flushing and rotating chunks as thresholds are hit.

        Line must already include its trailing newline.
        """
        self._write_buffer.append(line)
        if len(self._write_buffer) >= BATCH_SIZE:
            self._flush()
            if self._chunk_total >= CHUNK_SIZE:
                self._rotate()

    def _flush(self) -> None:
        """Write the buffered lines to the current chunk's files and clear it."""
        self._f.writelines(self._write_buffer)
        self._f_gz.writelines(self._write_buffer)
        self.total += len(self._write_buffer)
        self._chunk_total += len(self._write_buffer)
        self._write_buffer = []

    def _rotate(self) -> None:
        """Close, upload, and delete the current chunk, then open the next one."""
        self._f.close()
        self._f_gz.close()
        _upload_chunk(self._s3, self._output_file, self._output_file_gz)
        self._output_file.unlink()
        self._output_file_gz.unlink()
        self.chunks_uploaded += 1
        print(
            f"Uploaded chunk {self._chunk_index} "
            f"({self._output_file.name}, {self._chunk_total} passages) - "
            f"{self.total} passages written so far."
        )
        self._chunk_index += 1
        self._chunk_total = 0
        self._output_file, self._output_file_gz = _open_chunk(self._chunk_index)
        self._f = self._output_file.open("wb")
        self._f_gz = gzip.open(self._output_file_gz, "wb")

    def abort(self) -> None:
        """
        Close file handles without uploading, for the exception path.

        Matches the other materializers in this module (e.g.
        `documents_feed_materializer`): on error, nothing partial gets
        uploaded to S3 for the feeder to pick up.
        """
        self._f.close()
        self._f_gz.close()
        self._output_file.unlink(missing_ok=True)
        self._output_file_gz.unlink(missing_ok=True)

    def close(self) -> None:
        """Flush any remainder, close file handles, and upload the final chunk."""
        if self._write_buffer:
            self._flush()
        self._f.close()
        self._f_gz.close()

        if self._chunk_total > 0:
            _upload_chunk(self._s3, self._output_file, self._output_file_gz)
            self._output_file.unlink()
            self._output_file_gz.unlink()
            self.chunks_uploaded += 1
            print(
                f"Uploaded final chunk {self._chunk_index} "
                f"({self._output_file.name}, {self._chunk_total} passages)."
            )
        else:
            # Last chunk ended up empty because the final flush landed exactly
            # on a chunk boundary - nothing new to upload, clean up the empty
            # files.
            self._output_file.unlink(missing_ok=True)
            self._output_file_gz.unlink(missing_ok=True)


def passages_feed_materializer():
    principal_id_lookup = _build_principal_id_lookup()
    print(f"Built principal_id lookup for {len(principal_id_lookup)} documents.")
    _cleanup_source_cache(DOCUMENTS_CACHE)

    passage_concepts_lookup = _build_passage_concepts_lookup()
    print(f"Built passage concepts lookup for {len(passage_concepts_lookup)} passages.")
    _cleanup_source_cache(INFERENCE_RESULTS_CACHE_DIR)

    writer = _ChunkWriter(s3=boto3.client("s3"))
    try:
        for document_id, inference_result in read_embeddings_input_v2():
            pdf_data = inference_result.get("pdf_data")
            text_blocks = pdf_data.get("text_blocks") if pdf_data is not None else None
            if text_blocks is None:
                continue
            
            block_text_by_id = {b["id"]: b["text"] for b in text_blocks}
            principal_id = principal_id_lookup.get(document_id)
            for block in text_blocks:
                vespa_update = _text_block_to_vespa_update(
                    block,
                    document_id,
                    principal_id=principal_id,
                    concepts=passage_concepts_lookup.get(block["id"]),
                    block_text_by_id=block_text_by_id,
                )
                writer.append(orjson.dumps(vespa_update) + b"\n")
    except Exception:
        writer.abort()
        raise

    writer.close()
    _cleanup_source_cache(EMBEDDINGS_CACHE_DIR)

    print(
        f"Uploaded {writer.total} passages to S3 across "
        f"{writer.chunks_uploaded} chunk(s)."
    )


if __name__ == "__main__":
    passages_feed_materializer()
