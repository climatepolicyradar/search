"""CSV building for `GET /search/documents:download`."""

import csv
import io
import math
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from search.data_in_models import Document
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import DevVespaDocumentSearchEngine

EXCLUDED_LABEL_TYPES = {"topic", "concept"}

# Attribute/label columns are prefixed so they can never collide with the
# fixed columns (document_id, title, description) or with each other:
# `attributes` is unvalidated freeform metadata from Vespa, not a closed,
# trusted vocabulary, so an attribute key (or label type) could otherwise
# happen to equal a fixed column name and silently overwrite it in the row.
ATTRIBUTE_COLUMN_PREFIX = "attributes."
LABEL_COLUMN_PREFIX = "labels."


def _label_type_columns(documents: list[Document]) -> list[str]:
    """Distinct, non-excluded label types present across ``documents``, sorted."""
    types: set[str] = set()
    for document in documents:
        for label in document.labels:
            if label.type not in EXCLUDED_LABEL_TYPES:
                types.add(label.type)
    return sorted(f"{LABEL_COLUMN_PREFIX}{type_}" for type_ in types)


def _attribute_columns(documents: list[Document]) -> list[str]:
    """Distinct attribute keys present across ``documents``, sorted."""
    keys: set[str] = set()
    for document in documents:
        keys.update(document.attributes.keys())
    return sorted(f"{ATTRIBUTE_COLUMN_PREFIX}{key}" for key in keys)


def _row_for_document(
    document: Document, attribute_columns: list[str], label_columns: list[str]
) -> dict[str, str]:
    row: dict[str, str] = {
        "document_id": document.id,
        "title": document.title,
        "description": document.description or "",
    }
    for key in attribute_columns:
        value = document.attributes.get(key.removeprefix(ATTRIBUTE_COLUMN_PREFIX), "")
        row[key] = str(value)
    labels_by_type: dict[str, list[str]] = {}
    for label in document.labels:
        if label.type in EXCLUDED_LABEL_TYPES:
            continue
        labels_by_type.setdefault(label.type, []).append(label.value.value)
    for label_type in label_columns:
        row[label_type] = "; ".join(
            labels_by_type.get(label_type.removeprefix(LABEL_COLUMN_PREFIX), [])
        )
    return row


def build_csv_rows(documents: list[Document]) -> tuple[list[str], list[dict[str, str]]]:
    """
    Build the CSV header and rows for ``documents``.

    :param documents: Document search results, already capped to the
        request's ``max_results``.
    :return: ``(header, rows)`` — ``header`` is the full ordered column list,
        ``rows`` is one ``dict`` per document keyed by every column in
        ``header``.
    """
    attribute_columns = _attribute_columns(documents)
    label_columns = _label_type_columns(documents)
    header = ["document_id", "title", "description", *attribute_columns, *label_columns]
    rows = [
        _row_for_document(document, attribute_columns, label_columns)
        for document in documents
    ]
    return header, rows


DEFAULT_MAX_RESULTS = 500

# Comfortably under Vespa's own default `hits`/`offset` ceiling (~400), so a
# single `max_results` request never trips `VespaError` by asking one page
# for too much - see search/engines/dev_vespa.py's `_DEFAULT_DOCUMENT_TOTAL_TARGET_HITS`
# comment for the related weakAnd retrieval-depth issue this mirrors.
_INTERNAL_PAGE_SIZE = 100


def fetch_documents_for_download(
    engine: DevVespaDocumentSearchEngine,
    query: str | None,
    order_by: list[OrderBy],
    filters_json_string: str | None,
    max_results: int,
) -> list[Document]:
    """
    Fetch up to ``max_results`` documents, paging the engine internally.

    Pages are independent offset-based requests (``page_token`` maps directly
    to a Vespa ``offset``), so they're fetched concurrently rather than one
    round trip at a time. Results are then reassembled in page order and
    truncated at the first short/empty page - Vespa has no more matches past
    that point, mirroring the previous sequential early-stop behaviour.
    """
    page_count = math.ceil(max_results / _INTERNAL_PAGE_SIZE)
    page_sizes = [
        min(_INTERNAL_PAGE_SIZE, max_results - (page_token - 1) * _INTERNAL_PAGE_SIZE)
        for page_token in range(1, page_count + 1)
    ]

    def fetch_page(page_token: int, page_size: int) -> list[Document]:
        response = engine.search(
            query=query,
            pagination=Pagination(page_token=page_token, page_size=page_size),
            order_by=order_by,
            filters_json_string=filters_json_string,
        )
        return response.results

    with ThreadPoolExecutor(max_workers=page_count) as pool:
        pages = list(
            pool.map(fetch_page, range(1, page_count + 1), page_sizes)
        )

    results: list[Document] = []
    for page, page_size in zip(pages, page_sizes):
        results.extend(page)
        if len(page) < page_size:
            break
    return results[:max_results]


def generate_csv(documents: list[Document]) -> Iterator[str]:
    """
    Yield CSV text chunks for ``documents``: a header line, then one per row.

    Reuses one ``StringIO`` buffer across rows (``seek(0)`` + ``truncate(0)``
    between writes) rather than allocating a fresh one per row.
    """
    header, rows = build_csv_rows(documents)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(row)
        yield buffer.getvalue()
