"""API initialization and search engine factories."""

import logging
from pathlib import Path

from search.aws import download_file_from_s3, get_bucket_name
from search.engines.json import (
    JSONDocumentSearchEngine,
    JSONLabelSearchEngine,
    JSONPassageSearchEngine,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")

# Preferred search engine configuration
PREFERRED_ENGINES = {
    "documents": (JSONDocumentSearchEngine, "documents.jsonl"),
    "labels": (JSONLabelSearchEngine, "labels.jsonl"),
    "passages": (JSONPassageSearchEngine, "passages.jsonl"),
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
            download_file_from_s3(bucket_name, f"data/{filename}")
        except Exception as e:
            logger.error(f"Failed to download {name}: {e}")
            raise


def get_label_search_engine():
    """Get the label search engine instance."""
    engine_class, filename = PREFERRED_ENGINES["labels"]
    return engine_class(str(DATA_DIR / filename))


def get_passage_search_engine():
    """Get the passage search engine instance."""
    engine_class, filename = PREFERRED_ENGINES["passages"]
    return engine_class(str(DATA_DIR / filename))


def get_document_search_engine():
    """Get the document search engine instance."""
    engine_class, filename = PREFERRED_ENGINES["documents"]
    return engine_class(str(DATA_DIR / filename))
