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

import asyncio
import csv
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from search.data_in_models import Document, DocumentWithoutRelationships
from search.engines import ListResponse, OrderBy, Pagination
from search.engines.dev_vespa import Filter
from search.engines.dev_vespa.documents_search_engine import CollectionReference


class DocumentSearchEngine(Protocol):
    async def asearch(
            self,
            query: str | None,
            pagination: Pagination,
            order_by: list[OrderBy],
            filters: Filter | None = None,
        ) -> ListResponse[Document]:
        """Search documents."""
        ...

    async def collection_references(
            self,
            document_ids: list[str],
        ) -> dict[str, CollectionReference]:
        """Resolve collection references for the given document ids."""
        ...


class Echo:
    def write(self, value: str) -> str:
        """No-op file-like write to stream CSVs with"""
        return value

@dataclass
class DocumentWithCollection:
    collection: CollectionReference | None
    document: Document

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


def _labels(document: Document, relation_type: str) -> str:
    """Read semicolon separated labels of the given *relationship* type off the document"""
    return "; ".join(label.value.value for label in document.labels if label.type == relation_type)


def _label_type(document: Document, value_type: str) -> str:
    """Read semicolon separated labels of the given *label* type off the document"""
    return "; ".join(label.value.value for label in document.labels if label.value.type == value_type)


def _attribute(document: Document, key: str) -> str:
    """
    Take ``key`` out of a document's attributes, as text.

    An absent attribute gives ``""``, so a document missing one reads as
    an empty cell rather than failing the download. Attributes are typed
    ``str | float | bool``, so the value is stringified: `csv` would
    otherwise raise on a non-string only at write time, failing the whole
    download for one cell.
    """
    value = document.attributes.get(key)
    return "" if value is None else str(value)


class Column(StrEnum):
    ID = "ID"
    TITLE = "TITLE"
    DESCRIPTION = "DESCRIPTION"
    GEOGRAPHIES = "GEOGRAPHIES"
    PUBLISHED_DATE = "PUBLISHED_DATE"
    ENTITY_TYPE = "ENTITY_TYPE"
    CATEGORY = "CATEGORY"
    PROVIDER = "PROVIDER"
    COLLECTION_TITLE = "COLLECTION_TITLE"
    COLLECTION_DESCRIPTION = "COLLECTION_DESCRIPTION"
    BUNDLE_ID = "BUNDLE_ID"
    BUNDLE_TITLE = "BUNDLE_TITLE"
    CASE_STATUS = "CASE_STATUS"
    CASE_NUMBER = "CASE_NUMBER"
    AT_ISSUE = "AT_ISSUE"
    ORIGINAL_CASE_NAME = "ORIGINAL_CASE_NAME"
    PRINCIPAL_LAWS = "PRINCIPAL_LAWS"
    CASE_CATEGORIES = "CASE_CATEGORIES"
    JURISDICTIONS = "JURISDICTIONS"


def read_column(
        document: Document,
        collection: CollectionReference | None,
        column: Column
    ) -> str:
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
    The above column also belongs here but is absent until the data behind
    it exists. It is left out for now rather than offered empty.
    """
    match column:
        case Column.ID:
            return document.id
        case Column.TITLE:
            return document.title
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
            return collection and collection.title or ""
        case Column.COLLECTION_DESCRIPTION:
            return collection and collection.description or ""
        case Column.BUNDLE_ID:
            return collection and collection.id or ""
        case Column.BUNDLE_TITLE:
            return collection and collection.title or ""
        case Column.CASE_STATUS:
            return _attribute(document, "case_status")
        case Column.CASE_NUMBER:
            return _attribute(document, "identifier::case_number")
        case Column.AT_ISSUE:
            return _attribute(document, "core_object")
        case Column.ORIGINAL_CASE_NAME:
            return _attribute(document, "original_case_name")
        case Column.PRINCIPAL_LAWS:
            return _label_type(document, "principal_law")
        case Column.CASE_CATEGORIES:
            return _label_type(document, "case_category")
        case Column.JURISDICTIONS:
            return _label_type(document, "jurisdiction")


# Sent when a caller names no columns. Keeping a default means an ad-hoc
# caller - a person with curl, or an agent reading `llms.txt` - gets a
# usable CSV without first having to discover the column vocabulary.
DEFAULT_COLUMNS: list[Column] = [
    Column.ID,
    Column.TITLE,
    Column.DESCRIPTION,
    Column.GEOGRAPHIES,
    Column.PUBLISHED_DATE,
    Column.ENTITY_TYPE,
    Column.CATEGORY,
    Column.PROVIDER,
    Column.COLLECTION_TITLE,
]


async def fetch_csv(
    engine: DocumentSearchEngine,
    columns: list[Column] | None,
    query: str | None,
    order_by: list[OrderBy],
    filters: Filter | None,
    max_results: int,
    internal_page_size: int = 100,
) -> list[str]:
    """
    Build the CSV for a search, as a list of rows with the header first.

    The search is paged internally at `internal_page_size`, and every page is
    fetched concurrently, so the whole result set is in memory before the first
    row is returned.
    """

    deduped_columns = tuple(dict.fromkeys(columns or DEFAULT_COLUMNS))

    needs_collections = (
        Column.COLLECTION_DESCRIPTION in deduped_columns or
        Column.COLLECTION_TITLE in deduped_columns or
        Column.BUNDLE_TITLE in deduped_columns or
        Column.BUNDLE_ID in deduped_columns
    )

    header = [str(column) for column in deduped_columns]
    writer = csv.DictWriter(Echo(), fieldnames=header)
    output = [writer.writeheader()]

    page_count = math.ceil(max_results / internal_page_size)

    async def fetch_page(page: int) -> list[DocumentWithCollection]:
        results = await engine.asearch(
            pagination=Pagination(
                page_size=internal_page_size,
                page_token=page,
            ),
            order_by=order_by,
            filters=filters,
            query=query,
        )

        collections: dict[str, DocumentWithoutRelationships] = {}
        collection_references: dict[str, CollectionReference] = {}
        page_results: list[DocumentWithCollection] = []

        for item in results.results:
            for related in item.documents:
                if related.type == "member_of":
                    collections.setdefault(item.id, related.value)

        if needs_collections and (collection_ids := list(dict.fromkeys(stub.id for stub in collections.values()))):
            collection_references = await engine.collection_references(collection_ids)

        for result in results.results:
            collection_stub = collections.get(result.id)
            collection = collection_references.get(collection_stub.id) if collection_stub else None
            page_results.append(DocumentWithCollection(collection=collection, document=result))

        return page_results

    pages = await asyncio.gather(*[fetch_page(page) for page in range(1, page_count + 1)])
    for result in [result for page in pages for result in page][:max_results]:
        output.append(
            writer.writerow({
                str(column): read_column(result.document, result.collection, column)
                for column in deduped_columns
            })
        )

    return output
