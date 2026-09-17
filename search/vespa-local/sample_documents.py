"""
Build a local `documents` corpus for API performance testing.

Samples the same production Snowflake export that the `search-vespa-feeder-documents`
Prefect flow feeds (`vespa-feeder/documents_flow.py`), biased towards the documents
that are expensive to serve — the ones with the largest `passages` arrays — so that
local timings are dominated by the same summary-fetch cost that dominates production.

Two things end up in the corpus, and both are needed:

- **the largest documents** (`--largest`), which is the point of the exercise; and
- **a broad stride sample** (`--every`), which is what makes the largest ones
  measurable. The production-shaped queries in `perf.ts` filter on labels like
  `category::Report` and `status::Principal` and ask for facets; against a corpus of
  nothing but outliers most of them would match zero documents and time an empty
  result set.

Output (JSONL, ready for `vespa feed`, plus a manifest describing the run):

    .data_cache/vespa-local/documents.jsonl
    .data_cache/vespa-local/manifest.json

Usage:

    just gen-documents                          # defaults below
    just gen-documents --files all --largest 500
    just gen-documents --snapshot 20260915T083159Z
"""

import argparse
import heapq
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import boto3
from mypy_boto3_s3 import S3Client

# The two derivations the production feeder applies on the way into Vespa. Without
# them a locally fed document has no `id` and no `principal_id`, which is a
# different document from the one production serves — and `principal_id` in
# particular is a filterable attribute (search/engines/dev_vespa.py's
# documents_filter_field_to_vespa_field_map). Imported rather than reimplemented so
# this corpus cannot drift from what the feeder actually writes.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vespa-feeder"))
from documents_flow import derive_document_data  # noqa: E402

BUCKET = "cpr-prod-snowflake-data-export"
EXPORT_PREFIX = "production/published/pipeline_data_in_vespa_documents_updates_v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / ".data_cache" / "vespa-local"
OUT_PATH = OUT_DIR / "documents.jsonl"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# Enough part files to get a spread of geographies/categories without pulling the
# whole ~11GB export. At ~17MB each this is a sub-minute download on a normal
# connection; `--files all` is there when you want the real tail.
DEFAULT_FILES = 32
DEFAULT_LARGEST = 200
DEFAULT_EVERY = 5
DEFAULT_MAX_BYTES = 1 * 1024**3  # 1 GiB of JSONL
DEFAULT_WORKERS = 8


class SampleError(Exception):
    """The corpus could not be built from the production export."""


@dataclass(frozen=True, order=True)
class Candidate:
    """A document held as a candidate for the `--largest` slice of the corpus."""

    passage_count: int
    # Breaks ties without ever comparing the payload, and makes the selection
    # deterministic for a given (snapshot, file list) rather than dependent on the
    # order threads happened to finish in.
    sort_key: str
    document_id: str
    line: str


def newest_snapshot(s3: S3Client) -> str:
    """
    Name of the most recent immutable snapshot under the export prefix.

    Deliberately *not* `latest/`. The Snowflake export rewrites `latest/` in place
    over several minutes, so a read that straddles a publish gets some part files
    from the old export and some from the new. A timestamped snapshot is written
    once and never touched again, so a corpus built from it is reproducible — pass
    `--snapshot` with the name recorded in manifest.json to rebuild the same one.

    :raises SampleError: if the export prefix holds no timestamped snapshots.
    """
    paginator = s3.get_paginator("list_objects_v2")
    snapshots = [
        prefix["Prefix"].rstrip("/").rsplit("/", 1)[-1]
        for page in paginator.paginate(
            Bucket=BUCKET, Prefix=f"{EXPORT_PREFIX}/", Delimiter="/"
        )
        for prefix in page.get("CommonPrefixes", [])
    ]
    timestamped = sorted(name for name in snapshots if name != "latest")
    if not timestamped:
        raise SampleError(
            f"No timestamped snapshots under s3://{BUCKET}/{EXPORT_PREFIX}/ "
            f"(saw: {sorted(snapshots)})"
        )
    return timestamped[-1]


def list_part_keys(s3: S3Client, snapshot: str) -> list[str]:
    """
    Every `.jsonl` part file in a snapshot, sorted so `--files N` is reproducible.

    :raises SampleError: if the snapshot holds no part files.
    """
    paginator = s3.get_paginator("list_objects_v2")
    keys = sorted(
        obj["Key"]
        for page in paginator.paginate(
            Bucket=BUCKET, Prefix=f"{EXPORT_PREFIX}/{snapshot}/"
        )
        for obj in page.get("Contents", [])
        if obj["Key"].endswith(".jsonl")
    )
    if not keys:
        raise SampleError(
            f"No .jsonl part files at s3://{BUCKET}/{EXPORT_PREFIX}/{snapshot}/"
        )
    return keys


def stream_lines(s3: S3Client, key: str) -> Iterator[bytes]:
    """
    Stream one part file line by line, without landing it on disk.

    Part files are ~17MB each and `--files all` is 640 of them; streaming keeps the
    peak disk cost of a full scan at zero and the peak memory cost at one line.

    :raises SampleError: if the object cannot be read.
    """
    try:
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
        yield from body.iter_lines()
    except Exception as exc:
        raise SampleError(f"Failed reading s3://{BUCKET}/{key}: {exc}") from exc


def passage_count(record: dict[str, Any]) -> int:
    """How many passages a documents-update record assigns."""
    passages = record.get("fields", {}).get("passages", {}).get("assign")
    return len(passages) if isinstance(passages, list) else 0


def document_id(record: dict[str, Any]) -> str:
    """
    The Vespa document id a record targets, e.g. `id:documents:documents::CCLW...`.

    :raises SampleError: if the record carries neither an `update` nor a `put` key —
        it is then not a feedable record and silently dropping it would leave a
        corpus that is quietly smaller than the manifest claims.
    """
    for operation in ("update", "put"):
        if operation in record:
            return record[operation]
    raise SampleError(
        f"Record has no `update` or `put` key, so it cannot be fed: "
        f"keys={sorted(record)}"
    )


class Corpus:
    """
    Accumulates the sampled corpus across the download threads.

    The stride sample is written straight through to the output file as it is
    scanned (it is small, and holding it would put hundreds of MB on the heap); the
    `--largest` candidates are held in a bounded min-heap and written at the end,
    once the scan has seen enough documents to know which of them actually are the
    largest. The heap never holds more than `--largest` entries, so peak memory is
    the size of that slice of the corpus and not of everything scanned.
    """

    def __init__(self, out_file, largest: int, every: int) -> None:
        self._out_file = out_file
        self._largest = largest
        self._every = every
        self._lock = threading.Lock()
        self._heap: list[Candidate] = []

        self.written_ids: set[str] = set()
        self.bytes_written = 0
        self.documents_scanned = 0
        self.dropped_to_budget = 0

    def offer(self, record: dict[str, Any], index_in_file: int, part_name: str) -> None:
        """Consider one scanned record for both slices of the corpus."""
        record = derive_document_data(record)
        candidate = Candidate(
            passage_count=passage_count(record),
            sort_key=f"{part_name}:{index_in_file:08d}",
            document_id=document_id(record),
            line=json.dumps(record, separators=(",", ":")),
        )

        with self._lock:
            self.documents_scanned += 1
            if index_in_file % self._every == 0:
                self._write(candidate)
            # Candidate ordering is (passage_count, sort_key), so the root of the
            # heap is the smallest document currently held — the one to evict.
            heapq.heappush(self._heap, candidate)
            if len(self._heap) > self._largest:
                heapq.heappop(self._heap)

    def _write(self, candidate: Candidate) -> None:
        """Append one document to the feed file. Caller holds the lock."""
        if candidate.document_id in self.written_ids:
            return
        self._out_file.write(candidate.line + "\n")
        self.written_ids.add(candidate.document_id)
        self.bytes_written += len(candidate.line) + 1

    def finalise(self, max_bytes: int) -> list[Candidate]:
        """
        Append the largest documents, biggest first, until the byte budget runs out.

        :return: the candidates actually written, largest first.
        """
        kept: list[Candidate] = []
        for candidate in sorted(self._heap, reverse=True):
            if candidate.document_id in self.written_ids:
                continue  # already in via the stride sample
            if self.bytes_written + len(candidate.line) > max_bytes:
                self.dropped_to_budget += 1
                continue
            self._write(candidate)
            kept.append(candidate)
        return kept


def scan_part(s3: S3Client, key: str, corpus: Corpus) -> None:
    """
    Scan one part file into the corpus.

    :raises SampleError: on an unreadable object or a line that is not JSON. A part
        file that half-parses would produce a corpus that looks fine and is missing
        documents, so this fails the run instead.
    """
    part_name = key.rsplit("/", 1)[-1]
    for index, raw in enumerate(stream_lines(s3, key)):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SampleError(f"Malformed JSON at {part_name}:{index + 1}: {exc}") from exc
        corpus.offer(record, index, part_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Snapshot to sample, e.g. 20260915T083159Z. Defaults to the newest.",
    )
    parser.add_argument(
        "--files",
        default=str(DEFAULT_FILES),
        help=f"How many part files to scan, or 'all'. Default {DEFAULT_FILES}.",
    )
    parser.add_argument(
        "--largest",
        type=int,
        default=DEFAULT_LARGEST,
        help=f"Keep the N documents with the most passages. Default {DEFAULT_LARGEST}.",
    )
    parser.add_argument(
        "--every",
        type=int,
        default=DEFAULT_EVERY,
        help=f"Also keep every Nth document scanned. Default {DEFAULT_EVERY}.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Cap on the JSONL written. Default {DEFAULT_MAX_BYTES} (1 GiB).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent part-file downloads. Default {DEFAULT_WORKERS}.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Seed for which part files are picked when --files < all. Default 0.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    s3: S3Client = boto3.client("s3")

    snapshot = args.snapshot or newest_snapshot(s3)
    all_keys = list_part_keys(s3, snapshot)

    if args.files == "all":
        keys = all_keys
    else:
        try:
            wanted = int(args.files)
        except ValueError as exc:
            raise SampleError(f"--files must be an integer or 'all', got {args.files!r}") from exc
        # Sampled across the whole export rather than taking the first N: part files
        # are written per Snowflake micro-partition, so the first N are correlated
        # and would skew the corpus towards one slice of the document set.
        keys = sorted(random.Random(args.seed).sample(all_keys, min(wanted, len(all_keys))))

    print(f"snapshot  s3://{BUCKET}/{EXPORT_PREFIX}/{snapshot}/")
    print(f"scanning  {len(keys)} of {len(all_keys)} part files, {args.workers} at a time")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w") as out_file:
        corpus = Corpus(out_file, largest=args.largest, every=args.every)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            # list() so that an exception in any worker surfaces here rather than
            # being parked in an un-inspected future.
            list(pool.map(lambda key: scan_part(s3, key, corpus), keys))
        kept_largest = corpus.finalise(args.max_bytes)

    manifest = {
        "bucket": BUCKET,
        "snapshot": snapshot,
        "files_scanned": len(keys),
        "files_available": len(all_keys),
        "documents_scanned": corpus.documents_scanned,
        "documents_written": len(corpus.written_ids),
        "bytes_written": corpus.bytes_written,
        "largest_dropped_to_budget": corpus.dropped_to_budget,
        "args": {
            "files": args.files,
            "largest": args.largest,
            "every": args.every,
            "max_bytes": args.max_bytes,
            "seed": args.seed,
        },
        "largest_documents": [
            {"id": candidate.document_id, "passages": candidate.passage_count}
            for candidate in kept_largest[:10]
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"scanned   {corpus.documents_scanned} documents\n"
        f"wrote     {len(corpus.written_ids)} documents "
        f"({corpus.bytes_written / 1024**2:.1f} MiB) -> {OUT_PATH}"
    )
    if kept_largest:
        biggest = kept_largest[0]
        print(f"largest   {biggest.document_id} ({biggest.passage_count} passages)")
    if corpus.dropped_to_budget > 0:
        # Never a silent cap: a corpus that is quietly missing its heaviest
        # documents would make a perf run look better than the system is.
        print(
            f"WARNING   {corpus.dropped_to_budget} of the top {args.largest} documents "
            f"were left out by the --max-bytes budget "
            f"({args.max_bytes / 1024**2:.0f} MiB) — raise it to include them"
        )
    print(f"manifest  {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
