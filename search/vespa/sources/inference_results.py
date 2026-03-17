import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict

import orjson

from search.config import REPO_ROOT_DIR

DATA_CACHE_DIR = (
    REPO_ROOT_DIR / ".data_cache" / "vespa" / "sources" / "inference_results"
)


class InferenceResult(TypedDict):
    id: str
    name: str
    parent_concepts: list[str]
    parent_concept_ids_flat: str
    model: str
    end: int
    start: int
    timestamp: str


PassageId = str
InferenceResultInput = dict[PassageId, list[InferenceResult]]


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
                "s3://cpr-prod-data-pipeline-cache/inference_results/latest/",
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


def read() -> Iterator[tuple[str, InferenceResultInput]]:
    files = extract()
    for file in files:
        document_id = file.stem.replace("_translated_en", "")

        with open(file, "rb") as inference_file:
            inference_result: InferenceResultInput = orjson.loads(inference_file.read())
            yield document_id, inference_result
