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
from datetime import datetime
from enum import StrEnum

import httpx2
from pydantic import HttpUrl

from search.engines import OrderBy
from search.engines.dev_vespa import Filter
from search.engines.dev_vespa.documents_search_engine import (
    CollectionReference,
    DocumentSearchEngine,
    ExportDocument,
    ExportRow,
)


class Echo:
    def write(self, value: str) -> str:
        """No-op file-like write to stream CSVs with"""
        return value

def _published_date(document: ExportDocument) -> str:
    """
    Parse published date.

    ``published_date`` as ``YYYY-MM-DD``, or ``""`` when absent or
    unparse-able.

    Stored as an ISO 8601 timestamp (``2023-10-23T00:00:00Z``); the CSV wants
    the date alone. A value that will not parse yields an empty cell rather
    than failing the whole download.
    """
    raw = document.attributes_string.get("published_date")
    if raw is None:
        return ""
    try:
        return datetime.fromisoformat(raw).date().isoformat()
    except ValueError:
        return ""


def _labels(document: ExportDocument, relation_type: str) -> str:
    """Read semicolon separated labels of the given *relationship* type off the document"""
    return "; ".join(label.value for label in document.labels if label.relationship == relation_type)


def _label_type(document: ExportDocument, value_type: str) -> str:
    """Read semicolon separated labels of the given *label* type off the document"""
    return "; ".join(label.value for label in document.labels if label.type == value_type)


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
    BUNDLE_DESCRIPTION = "BUNDLE_DESCRIPTION"
    CASE_STATUS = "CASE_STATUS"
    CASE_NUMBER = "CASE_NUMBER"
    AT_ISSUE = "AT_ISSUE"
    ORIGINAL_CASE_NAME = "ORIGINAL_CASE_NAME"
    PRINCIPAL_LAWS = "PRINCIPAL_LAWS"
    CASE_CATEGORIES = "CASE_CATEGORIES"
    JURISDICTIONS = "JURISDICTIONS"
    URL = "URL"
    COLLECTION_URL = "COLLECTION_URL"
    BUNDLE_URL = "BUNDLE_URL"


class BaseUrlRequired(Exception):
    pass


_URL_COLUMNS = (Column.URL, Column.COLLECTION_URL, Column.BUNDLE_URL)


def _page_url(base_url: HttpUrl, page: str, slug: str) -> str:
    return str(httpx2.URL(str(base_url)).copy_with(path=f"/{page}/{slug}"))


def read_column(
        document: ExportDocument,
        collection: CollectionReference | None,
        column: Column,
        base_url: HttpUrl | None,
    ) -> str:
    """
    One cell's text: the field ``column`` names, off ``document``.

    A column name always means the same data wherever it is asked for. Two
    names may read the same source - `COLLECTION_TITLE` and
    `BUNDLE_TITLE` are the same collection field under the name a given app
    uses for it - but a name never changes what it reads depending on who
    is asking.

    Matching on the column rather than looking a reader up in a table means
    a column added to `Column` without a branch here is a type error, not a
    `KeyError` part-way through a download.
    """
    match column:
        case Column.ID:
            return document.id
        case Column.TITLE:
            return document.title or ""
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
        case Column.COLLECTION_TITLE | Column.BUNDLE_TITLE:
            return collection and collection.title or ""
        case Column.COLLECTION_DESCRIPTION | Column.BUNDLE_DESCRIPTION:
            return collection and collection.description or ""
        case Column.BUNDLE_ID:
            return collection and collection.id or ""
        case Column.CASE_STATUS:
            return document.attributes_string.get("case_status", "")
        case Column.CASE_NUMBER:
            return document.attributes_string.get("identifier::case_number", "")
        case Column.AT_ISSUE:
            return document.attributes_string.get("core_object", "")
        case Column.ORIGINAL_CASE_NAME:
            return document.attributes_string.get("original_case_name", "")
        case Column.PRINCIPAL_LAWS:
            return _label_type(document, "principal_law")
        case Column.CASE_CATEGORIES:
            return _label_type(document, "case_category")
        case Column.JURISDICTIONS:
            return _label_type(document, "jurisdiction")
        case Column.URL:
            return _page_url(base_url, "document", document.slug) if base_url and document.slug else ""
        case Column.COLLECTION_URL | Column.BUNDLE_URL:
            return _page_url(base_url, "collections", collection.slug) if base_url and collection and collection.slug else ""


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
    base_url: HttpUrl | None,
) -> list[str]:
    """
    Build the CSV for a search, as a list of rows with the header first.

    One request for the whole file. `max_results` is capped at 500 by the
    route, and the export reads only attributes, so there is nothing to spread
    across pages: paging it re-ran the match and rank once per page and threw
    all but one page's worth away.
    """

    deduped_columns = tuple(dict.fromkeys(columns or DEFAULT_COLUMNS))

    if base_url is None and any(column in deduped_columns for column in _URL_COLUMNS):
        raise BaseUrlRequired()

    needs_collections = (
        Column.COLLECTION_DESCRIPTION in deduped_columns or
        Column.COLLECTION_TITLE in deduped_columns or
        Column.BUNDLE_TITLE in deduped_columns or
        Column.BUNDLE_DESCRIPTION in deduped_columns or
        Column.BUNDLE_ID in deduped_columns or
        Column.COLLECTION_URL in deduped_columns or
        Column.BUNDLE_URL in deduped_columns
    )

    header = [str(column) for column in deduped_columns]
    writer = csv.DictWriter(Echo(), fieldnames=header)
    output = [writer.writeheader()]

    rows: list[ExportRow] = await engine.export(
        query=query,
        limit=max_results,
        order_by=order_by,
        filters=filters,
        resolve_collections=needs_collections,
    )

    for row in rows:
        output.append(
            writer.writerow({
                str(column): read_column(
                    document=row.document,
                    collection=row.collection,
                    column=column,
                    base_url=base_url,
                )
                for column in deduped_columns
            })
        )

    return output
