"""
CSV building for `GET /search/documents:download`.

A download's columns are chosen by the caller, from a closed vocabulary
this module defines. The caller sends the column names it wants, in the
order it wants them; this module owns what each name means.

Column names and their intended per-app sets come from the agreed field
mapping:
@see https://docs.google.com/spreadsheets/d/1nc_0WtsU2syWcX-iB9iqW4hEYJAYduLQhW2pV1r0e3I

They are deliberately not derived from whatever attributes and labels
happen to appear in a result set, as that made the columns vary between
two download datasets on the same app (as `download this search` - which
is what this module contains logic for - is powered by Vespa, but
`download all data` is powered by Snowflake), so downloads could not be
relied on to have a stable shape by our users.

The API does not know which app is asking. A caller that wants a
particular app's column set sends that set; the mapping from app to
columns lives with the caller, not here.
"""

import csv
import io
import math
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import StrEnum

from search.data_in_models import Document, DocumentWithoutRelationships
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import DevVespaDocumentSearchEngine, Filter


def _published_date(document: Document) -> str:
    """
    Parse published date.

    ``published_date`` as ``YYYY-MM-DD``, or ``""`` when absent or
    unparse-able.

    Stored as an ISO 8601 timestamp (``2023-10-23T00:00:00Z``); the CSV wants
    the date alone. A value that will not parse yields an empty cell rather
    than failing the whole download.
    """
    raw = document.attributes.get("published_date")
    if not isinstance(raw, str):
        return ""
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return ""


def _labels(document: Document, label_type: str) -> str:
    """
    Join the label values of one type.

    A document often carries more than one label of the same type, and the
    CSV gives each type a single cell, so every value goes in it:

    - _labels(document, "geography")  # "Europe & Central Asia; Germany"
    - _labels(document, "category")   # "Policy"

    A document with no label of this type gives ``""``, an empty cell.
    """
    _LABEL_VALUE_SEPARATOR = "; "

    return _LABEL_VALUE_SEPARATOR.join(
        label.value.value for label in document.labels if label.type == label_type
    )


def _collection(document: Document) -> DocumentWithoutRelationships | None:
    """
    The collection a document belongs to, or ``None``.

    A document that belongs to no collection gives ``None``, so a column
    reading off it is empty rather than failing the download.
    """
    # The relationship from a principal to the collection it belongs to. The
    # reverse (`has_member`) points at the principal's own documents, not a
    # collection, so we can't get a collection that way.
    _COLLECTION_RELATIONSHIP = "member_of"

    for relationship in document.documents:
        if relationship.type == _COLLECTION_RELATIONSHIP:
            return relationship.value
    return None


class Column(StrEnum):
    """
    A column a caller may ask for.

    The closed vocabulary of column names. A caller names columns from
    this enum, so an unknown name is rejected by FastAPI before any
    Vespa query runs, and the set of valid names is published in the
    OpenAPI schema rather than having to be known out of band.
    """

    ID = "ID"
    TITLE = "TITLE"
    DESCRIPTION = "DESCRIPTION"
    GEOGRAPHIES = "GEOGRAPHIES"
    PUBLISHED_DATE = "PUBLISHED_DATE"
    ENTITY_TYPE = "ENTITY_TYPE"
    CATEGORY = "CATEGORY"
    PROVIDER = "PROVIDER"
    COLLECTION_TITLE = "COLLECTION_TITLE"


def read_column(document: Document, column: Column) -> str:
    """
    One cell's text: the field ``column`` names, off ``document``.

    A column name always means the same data wherever it is asked for. Two
    names may read the same source - `COLLECTION_TITLE` and a future
    `BUNDLE_TITLE` are the same collection field under the name a given app
    uses for it - but a name never changes what it reads depending on who
    is asking.

    Matching on the column rather than looking a reader up in a table means
    a column added to `Column` without a branch here is a type error, not a
    `KeyError` part-way through a download.

    TODO: FUS-819 - URL
    TODO: FUS-820 - COLLECTION_DESCRIPTION
    The above columns also belong here but are absent until the data behind
    them exists. They are left out for now rather than offered empty.
    """
    match column:
        case Column.ID:
            return document.id
        case Column.TITLE:
            return document.title
        # `description` is optional on a document, so a missing value gives
        # an empty cell rather than the string `"None"`.
        case Column.DESCRIPTION:
            return document.description or ""
        case Column.GEOGRAPHIES:
            return _labels(document, "geography")
        case Column.PUBLISHED_DATE:
            return _published_date(document)
        case Column.ENTITY_TYPE:
            return _labels(document, "entity_type")
        case Column.CATEGORY:
            return _labels(document, "category")
        case Column.PROVIDER:
            return _labels(document, "provider")
        case Column.COLLECTION_TITLE:
            collection = _collection(document)
            return collection.title if collection else ""


# Sent when a caller names no columns. Keeping a default means an ad-hoc
# caller - a person with curl, or an agent reading `llms.txt` - gets a
# usable CSV without first having to discover the column vocabulary.
DEFAULT_COLUMNS: tuple[Column, ...] = (
    Column.ID,
    Column.TITLE,
    Column.DESCRIPTION,
    Column.GEOGRAPHIES,
    Column.PUBLISHED_DATE,
    Column.ENTITY_TYPE,
    Column.CATEGORY,
    Column.PROVIDER,
    Column.COLLECTION_TITLE,
)


def resolve_columns(columns: list[Column] | None) -> tuple[Column, ...]:
    """
    The columns to emit, in the order they were asked for.

    Duplicates are dropped, keeping each column's first position, so a
    repeated name cannot produce two identically-named CSV columns (which
    `csv.DictWriter` would write twice from one key) or shift the rest of
    the header out of the order the caller asked for.

    :param columns: The caller's columns, or ``None`` when it named none.
    :return: The resolved columns; `DEFAULT_COLUMNS` when none were named.
    """
    if not columns:
        return DEFAULT_COLUMNS
    return tuple(dict.fromkeys(columns))


def fetch_documents_for_download(
    engine: DevVespaDocumentSearchEngine,
    query: str | None,
    order_by: list[OrderBy],
    filters: Filter | None,
    max_results: int,
    internal_page_size: int = 100,
) -> list[Document]:
    """
    Fetch up to ``max_results`` documents, paging the engine internally.

    Pages are independent offset-based requests (``page_token`` maps directly
    to a Vespa ``offset``), so they're fetched concurrently rather than one
    round trip at a time. Results are then reassembled in page order and
    truncated at the first short/empty page - Vespa has no more matches past
    that point, mirroring the previous sequential early-stop behaviour.

    :param internal_page_size int: Default value is 100 as this is under
        Vespa's own default `hits`/`offset` ceiling (~400), so a single
        `max_results` request never trips `VespaError` by asking one page
        for too much.
        @see `_DEFAULT_DOCUMENT_TOTAL_TARGET_HITS` comment for the related
        weakAnd retrieval-depth issue this mirrors.
    """
    page_count = math.ceil(max_results / internal_page_size)
    page_sizes = [
        min(internal_page_size, max_results - (page_token - 1) * internal_page_size)
        for page_token in range(1, page_count + 1)
    ]

    def fetch_page(page_token: int, page_size: int) -> list[Document]:
        response = engine.search(
            query=query,
            pagination=Pagination(page_token=page_token, page_size=page_size),
            order_by=order_by,
            filters=filters,
        )
        return response.results

    with ThreadPoolExecutor(max_workers=page_count) as pool:
        pages = list(pool.map(fetch_page, range(1, page_count + 1), page_sizes))

    results: list[Document] = []
    for page, page_size in zip(pages, page_sizes):
        results.extend(page)
        if len(page) < page_size:
            break
    return results[:max_results]


def build_csv_rows(
    documents: list[Document], columns: list[Column] | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Build the CSV header and rows for ``documents``.

    :param documents: Document search results, already capped to the
        request's ``max_results``.
    :param columns: The columns to emit, in order. ``None`` or empty gives
        `DEFAULT_COLUMNS`.
    :return: ``(header, rows)`` - ``rows`` is one ``dict`` per document,
        keyed by every column in ``header``.
    """
    resolved = resolve_columns(columns)
    rows = [
        {str(column): read_column(document, column) for column in resolved}
        for document in documents
    ]
    return [str(column) for column in resolved], rows


def generate_csv(
    documents: list[Document], columns: list[Column] | None = None
) -> Iterator[str]:
    """
    Yield CSV text chunks for ``documents``: a header line, then one per row.

    Reuses one ``StringIO`` buffer across rows (``seek(0)`` + ``truncate(0)``
    between writes) rather than allocating a fresh one per row.
    """
    header, rows = build_csv_rows(documents, columns=columns)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(row)
        yield buffer.getvalue()
