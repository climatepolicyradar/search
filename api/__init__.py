"""API initialization and search engine factories."""

import logging

from search.aws import download_file_from_s3, get_bucket_name
from search.config import DATA_DIR
from search.engines import DocumentSearchEngine, LabelSearchEngine, PassageSearchEngine
from search.engines.duckdb import (
    DuckDBDocumentSearchEngine,
    DuckDBLabelSearchEngine,
    DuckDBPassageSearchEngine,
)

logger = logging.getLogger(__name__)

# Preferred search engine configuration
PREFERRED_ENGINES = {
    "documents": (DuckDBDocumentSearchEngine, "documents.duckdb"),
    "labels": (DuckDBLabelSearchEngine, "labels.duckdb"),
    "passages": (DuckDBPassageSearchEngine, "passages.duckdb"),
}


async def download_required_datasets_from_s3():
    """Download the datasets required by the preferred search engines from S3."""
    bucket_name = get_bucket_name()

    for name, (_, filename) in PREFERRED_ENGINES.items():
        if (DATA_DIR / filename).exists():
            logger.info(f"Skipping {name} ({filename})")
            continue

        try:
            logger.info(f"Downloading {name}: {filename}")
            download_file_from_s3(bucket_name, filename)
        except Exception as e:
            logger.error(f"Failed to download {name}: {e}")
            raise


def get_label_search_engine() -> LabelSearchEngine:
    """Get the label search engine instance."""
    engine_class, filename = PREFERRED_ENGINES["labels"]
    return engine_class(str(DATA_DIR / filename))


def get_passage_search_engine() -> PassageSearchEngine:
    """Get the passage search engine instance."""
    engine_class, filename = PREFERRED_ENGINES["passages"]
    return engine_class(str(DATA_DIR / filename))


def get_document_search_engine() -> DocumentSearchEngine:
    """Get the document search engine instance."""
    engine_class, filename = PREFERRED_ENGINES["documents"]
    return engine_class(str(DATA_DIR / filename))
