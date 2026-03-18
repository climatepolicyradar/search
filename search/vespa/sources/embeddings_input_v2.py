import subprocess
from pathlib import Path
from typing import Iterator, TypedDict

import orjson

from search.config import REPO_ROOT_DIR

DATA_CACHE_DIR = (
    REPO_ROOT_DIR / ".data_cache" / "vespa" / "sources" / "embeddings_input_v2"
)


class Coordinate(TypedDict):
    x: float
    y: float


class BoundingBox(TypedDict):
    coordinates: list[Coordinate]


class PageRef(TypedDict):
    number: int
    bounding_boxes: list[BoundingBox]


class TextBlock(TypedDict):
    language: str
    type: str
    type_confidence: float
    text: str
    id: str
    idx: int
    pages: list[PageRef]


class PdfData(TypedDict):
    text_blocks: list[TextBlock]


class EmbeddingsInputV2(TypedDict):
    document_id: str
    pdf_data: PdfData


def extract() -> list[Path]:
    if not DATA_CACHE_DIR.exists():
        print(
            f"{DATA_CACHE_DIR} cache missing. Downloading files to {DATA_CACHE_DIR}..."
        )
        subprocess.run(
            [
                "aws",
                "s3",
                "sync",
                "s3://cpr-prod-data-pipeline-cache/embeddings_input_v2/",
                str(DATA_CACHE_DIR),
                "--exclude",
                "*",
                "--include",
                "*.json",
            ],
            check=True,
        )
    else:
        print(f"{DATA_CACHE_DIR} already exists. Using cached files.")

    files = list(DATA_CACHE_DIR.glob("*.json"))
    return files


def read() -> Iterator[tuple[str, EmbeddingsInputV2]]:
    files = extract()
    for file in files:
        document_id = file.stem.replace("_translated_en", "")

        with open(file, "rb") as inference_file:
            inference_result: EmbeddingsInputV2 = orjson.loads(inference_file.read())
            yield document_id, inference_result
