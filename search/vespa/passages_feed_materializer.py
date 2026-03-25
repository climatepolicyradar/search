import gzip
from pathlib import Path
from typing import TypedDict

import boto3
import orjson

from search.vespa.models import VespaAssign, VespaUpdate
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


BATCH_SIZE = 10_000


def passages_feed_materializer():
    total = 0
    batch: list[bytes] = []

    output_file = OUTPUT_CACHE_DIR / "passages_feed_materializer.jsonl"
    output_file_gz = OUTPUT_CACHE_DIR / "passages_feed_materializer.jsonl.gz"
    with output_file.open("wb") as f, gzip.open(output_file_gz, "wb") as f_gz:
        for document_id, inference_result in read_embeddings_input_v2():
            pdf_data = inference_result.get("pdf_data")
            text_blocks = pdf_data.get("text_blocks") if pdf_data is not None else None
            if text_blocks is None:
                continue

            for block in text_blocks:
                passage: VespaPassage = {
                    "id": block["id"],
                    "idx": block["idx"],
                    "language": block["language"],
                    "text": block["text"],
                    "document_id": document_id,
                }
                vespa_update: VespaUpdate[VespaPassageUpdate] = {
                    "update": f"id:passages:passages::{passage['id']}",
                    "create": True,
                    "fields": {
                        "id": {"assign": passage["id"]},
                        "idx": {"assign": passage["idx"]},
                        "language": {"assign": passage["language"]},
                        "text": {"assign": passage["text"]},
                        "document_id": {"assign": passage["document_id"]},
                    },
                }
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
