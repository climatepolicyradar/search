from pathlib import Path

from search.engines import SearchEngine
from search.engines.json import (
    JSONDocumentSearchEngine,
    JSONLabelSearchEngine,
    JSONPassageSearchEngine,
)


def get_label_search_engine() -> SearchEngine:
    """Get the label search engine instance."""
    return JSONLabelSearchEngine(str(Path("data/labels.jsonl")))


def get_passage_search_engine() -> SearchEngine:
    """Get the passage search engine instance."""
    return JSONPassageSearchEngine(str(Path("data/passages.jsonl")))


def get_document_search_engine() -> SearchEngine:
    """Get the document search engine instance."""
    return JSONDocumentSearchEngine(str(Path("data/documents.jsonl")))
