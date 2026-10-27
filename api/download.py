"""
CSV building for `GET /search/documents:download`.

A download's columns are fixed per theme, named and ordered by the
agreed field mapping:
@see https://docs.google.com/spreadsheets/d/1nc_0WtsU2syWcX-iB9iqW4hEYJAYduLQhW2pV1r0e3I

They are deliberately not derived from whatever attributes and labels
happen to appear in a result set, as that made the columns vary between
two download datasets on the same app (as `download this search` - which
is what this module contains logic for - is powered by Vespa, but
`download all data` is powered by Snowflake), so downloads could not be
relied on to have a stable shape by our users.

"""

import csv
import io
import math
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import StrEnum

from search.data_in_models import Document
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import DevVespaDocumentSearchEngine, Filter


########################################################################
# Helper functions
########################################################################
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

def _labels(label_type: str, document: Document) -> str:
    """
    Return joined label values of the same type.

    A document often carries more than one label of the same type, and the
    CSV gives each type a single cell, so every value goes in it:

    - _labels("geography", document)  # "Europe & Central Asia; Germany"
    - _labels("category", document)   # "Policy"

    A document with no label of this type gives ``""``, an empty cell.
    Otherwise one cell's worth of label values, separated by ``"; "``.
    """
    # Separates the values of a column read from several labels of one type.
    _LABEL_VALUE_SEPARATOR = "; "

    return _LABEL_VALUE_SEPARATOR.join(
        label.value.value for label in document.labels if label.type == label_type
    )

def _collection_title(document: Document) -> str:
    """The title of the collection this document belongs to, or ``""``."""

    # The relationship from a principal to the collection it belongs to. The
    # reverse (`has_member`) points at the principal's own documents, not a
    # collection, so we can't get a collection title that way.
    _COLLECTION_RELATIONSHIP = "member_of"

    for relationship in document.documents:
        if relationship.type == _COLLECTION_RELATIONSHIP:
            return relationship.value.title
    return ""

########################################################################
# Theme/schema specific
########################################################################

# A schema is an ordered mapping of column name to the function that reads
# it from a document. Names and order live in one declaration so the two
# cannot drift apart.
CsvSchema = Mapping[str, Callable[[Document], str]]

# Set default schema for all apps.
#
# TODO: FUS-819 - URL
# TODO: FUS-820 - COLLECTION_DESCRIPTION 
# The above fields also belong here but are absent until the data
# behind them exists. They are left out for now rather than left as
# empty.
DEFAULT_SCHEMA: CsvSchema = {
    "ID": lambda document: document.id,
    "TITLE": lambda document: document.title,
    "DESCRIPTION": lambda document: document.description or "",
    "GEOGRAPHIES": lambda document: _labels("geography", document),
    "PUBLISHED_DATE": _published_date,
    "ENTITY_TYPE": lambda document: _labels("entity_type", document),
    "CATEGORY": lambda document: _labels("category", document),
    "PROVIDER": lambda document: _labels("provider", document),
    "COLLECTION_TITLE": _collection_title,
}

class Theme(StrEnum):
    """An app a download can be requested from."""

    CPR = "cpr"
    CCLW = "cclw"
    MCF = "mcf"
    CCC = "ccc"

# CPR, CCLW and MCF currently want identical columns, so they share one
# schema. To give one of them its own columns, add an entry to `SCHEMAS`
# below.
SCHEMAS: dict[Theme, CsvSchema] = {
    Theme.CPR: DEFAULT_SCHEMA,
    Theme.CCLW: DEFAULT_SCHEMA,
    Theme.MCF: DEFAULT_SCHEMA,
    # TODO FUS-675: CCC's columns are different.
    Theme.CCC: DEFAULT_SCHEMA, 
}

def schema_for_theme(theme: Theme | None) -> CsvSchema:
    """
    The schema for ``theme``, falling back to `DEFAULT_SCHEMA`.

    A caller that sends no theme - or one this API has not heard of, such as
    a newer app against an older deployment - still gets a usable CSV rather
    than an error.
    """
    if theme is None:
        return DEFAULT_SCHEMA
    return SCHEMAS.get(theme, DEFAULT_SCHEMA)

########################################################################
# Building the CSV
########################################################################

DEFAULT_MAX_RESULTS = 500

def build_csv_rows(
    documents: list[Document], theme: Theme | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    """
    Build the CSV header and rows for ``documents``.

    :param documents: Document search results, already capped to the
        request's ``max_results``.
    :param theme: The app the download was requested from, which selects
        the column set.
    :return: ``(header, rows)`` - ``rows`` is one ``dict`` per document,
        keyed by every column in ``header``.
    """
    schema = schema_for_theme(theme)
    rows = [
        {name: read(document) for name, read in schema.items()}
        for document in documents
    ]
    return list(schema), rows

def fetch_documents_for_download(
    engine: DevVespaDocumentSearchEngine,
    query: str | None,
    order_by: list[OrderBy],
    filters: Filter | None,
    max_results: int,
    internal_page_size: int = 100
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
        pages = list(
            pool.map(fetch_page, range(1, page_count + 1), page_sizes)
        )

    results: list[Document] = []
    for page, page_size in zip(pages, page_sizes):
        results.extend(page)
        if len(page) < page_size:
            break
    return results[:max_results]

def generate_csv(
    documents: list[Document], theme: Theme | None = None
) -> Iterator[str]:
    """
    Yield CSV text chunks for ``documents``: a header line, then one per row.

    Reuses one ``StringIO`` buffer across rows (``seek(0)`` + ``truncate(0)``
    between writes) rather than allocating a fresh one per row.
    """
    header, rows = build_csv_rows(documents, theme=theme)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(row)
        yield buffer.getvalue()
