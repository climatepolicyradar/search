"""Tests for `GET /search/documents:download`."""

from http import HTTPStatus

import httpx2
from fastapi.testclient import TestClient

from search.engines.dev_vespa.documents_search_engine import (
    CollectionReference,
    ExportDocument,
    ExportRow,
)
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)


def _row(
        id: str,
        title: str = "t",
        description: str | None = None,
        collection: CollectionReference | None = None,
        slug: str | None = None,
    ) -> ExportRow:
    return ExportRow(
        document=ExportDocument(id=id, title=title, description=description, slug=slug),
        collection=collection,
    )


def _download(
        test_client: TestClient,
        query: str = "toxic",
        columns: list[str] | None = None,
        max_results: int | None = None,
        msm: float | None = None,
        base_url: str | None = None,
    ) -> httpx2.Response:
    params: list[tuple[str, str]] = [("query", query)]
    if columns is not None:
        params.extend(("columns", column) for column in columns)
    if max_results is not None:
        params.append(("max_results", str(max_results)))
    if msm is not None:
        params.append(("msm", str(msm)))
    if base_url is not None:
        params.append(("base_url", base_url))
    return test_client.get("/search/documents:download", params=tuple(params))


def test_download_returns_csv_with_content_disposition(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:

    stub_engine.add_export_response([_row("doc-1", "A Climate Document")])

    response = _download(test_client)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "doc-1" in response.text


def test_download_asks_for_the_whole_file_in_one_request(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:
    """
    `max_results` is the page size, and there is only one page.

    The export reads attributes only, so there is nothing to spread across
    pages; paging re-ran the match and rank once per page for one page's worth
    of rows.
    """
    stub_engine.add_export_response([_row(f"doc-{i}") for i in range(500)])

    response = _download(test_client)

    assert response.status_code == HTTPStatus.OK
    assert [request.limit for request in stub_engine.export_requests] == [500]


def test_download_respects_max_results_query_param(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:
    stub_engine.add_export_response([_row(f"doc-{i}") for i in range(5)])

    response = _download(test_client, max_results=5)

    assert stub_engine.export_requests[0].limit == 5
    body_rows = response.text.strip().splitlines()[1:]
    assert len(body_rows) == 5


def test_download_rejects_non_positive_max_results(test_client: TestClient) -> None:
    assert _download(test_client, max_results=0).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_download_rejects_out_of_range_msm(test_client: TestClient) -> None:
    assert _download(test_client, msm=1.1).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_download_emits_the_requested_columns_in_order(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """The caller names the columns and their order; the API supplies them."""
    stub_engine.add_export_response([_row("doc-1", "A Climate Document")])

    response = _download(test_client, columns=["TITLE", "ID"])

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[0] == "TITLE,ID"


def test_download_without_columns_still_returns_a_csv(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """`columns` is optional, so an ad-hoc caller gets a usable CSV."""
    stub_engine.add_export_response([_row("doc-1", "A Climate Document")])

    response = _download(test_client)
    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[0].startswith("ID,TITLE,DESCRIPTION")


def test_download_rejects_a_column_the_api_does_not_know(test_client: TestClient) -> None:
    """
    An unknown column is a client error, not a silent omission.

    The caller asked for data it expects to find in the file. Dropping the
    column quietly would hand back a CSV that is missing a column the
    caller believes it requested, so say so instead.
    """
    response = _download(test_client, columns=["NOPE"])
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_download_writes_the_collection_resolved_for_a_row(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    collection = CollectionReference(id="collection-1", title="A Collection", description="About it")
    stub_engine.add_export_response([_row("doc-1", "A Climate Document", collection=collection)])

    response = _download(
        test_client,
        columns=["ID", "COLLECTION_TITLE", "COLLECTION_DESCRIPTION"],
    )

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[1] == "doc-1,A Collection,About it"


def test_download_reads_collection_fields_under_their_ccc_names(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    collection = CollectionReference(id="collection-1", title="A Collection", description="About it")
    stub_engine.add_export_response([_row("doc-1", "A Climate Document", collection=collection)])

    response = _download(
        test_client,
        columns=["BUNDLE_ID", "BUNDLE_TITLE", "BUNDLE_DESCRIPTION"],
    )

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[1] == "collection-1,A Collection,About it"


def test_download_leaves_collection_columns_blank_without_a_collection(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    stub_engine.add_export_response([_row("doc-1", "A Climate Document")])

    response = _download(test_client, columns=["ID", "COLLECTION_TITLE"])

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[1] == "doc-1,"


def test_download_asks_for_collections_only_when_a_column_needs_them(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """
    A download of plain document columns should not pay for the collection lookup.

    `resolve_collections` is what spares it: without it the engine makes a
    second Vespa call per page for a value no column reads.
    """
    stub_engine.add_export_response([_row("doc-1")])
    _download(test_client, columns=["ID", "TITLE"])

    stub_engine.add_export_response([_row("doc-2")])
    _download(test_client, columns=["ID", "COLLECTION_TITLE"])

    requested = [request.resolve_collections for request in stub_engine.export_requests]
    assert requested == [False, True]


def test_download_builds_urls_from_the_callers_base_url(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """The caller owns the host; the API appends the slug it holds."""
    collection = CollectionReference(id="collection-1", title="A Collection", slug="a-collection")
    stub_engine.add_export_response([_row("doc-1", collection=collection, slug="a-document")])

    response = _download(
        test_client,
        columns=["URL", "BUNDLE_URL"],
        base_url="https://www.climatecasechart.com",
    )

    expected = (
        "https://www.climatecasechart.com/document/a-document,"
        "https://www.climatecasechart.com/collections/a-collection"
    )
    assert response.text.splitlines()[1] == expected


def test_download_does_not_double_the_slash_after_a_trailing_slash(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    stub_engine.add_export_response([_row("doc-1", slug="a-document")])

    response = _download(
        test_client,
        columns=["URL"],
        base_url="https://www.climatecasechart.com/",
    )

    assert response.text.splitlines()[1] == "https://www.climatecasechart.com/document/a-document"


def test_download_leaves_the_url_blank_for_a_document_without_a_slug(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """
    Around 4% of principals carry no slug.

    There is no page to link to, so the cell is empty - but the row, and the
    rest of the download, are still correct and still a 200.
    """
    stub_engine.add_export_response([_row("doc-1", slug=None)])

    response = _download(test_client, columns=["ID", "URL"], base_url="https://example.org")

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[1] == "doc-1,"


def test_download_leaves_the_bundle_url_blank_without_a_collection(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    stub_engine.add_export_response([_row("doc-1", slug="a-document")])

    response = _download(test_client, columns=["ID", "BUNDLE_URL"], base_url="https://example.org")

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[1] == "doc-1,"


def test_download_rejects_a_url_column_without_a_base_url(test_client: TestClient) -> None:
    """
    A URL column with no host to build from is the caller's error, not an empty column.

    Answering 200 with a blank URL would be indistinguishable from the
    no-slug case above, which is a legitimate result.
    """
    response = _download(test_client, columns=["ID", "URL"])

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_download_without_a_url_column_does_not_need_a_base_url(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    stub_engine.add_export_response([_row("doc-1")])

    response = _download(test_client, columns=["ID", "TITLE"])

    assert response.status_code == HTTPStatus.OK


def test_download_asks_for_collections_when_only_the_bundle_url_is_wanted(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """
    `BUNDLE_URL` is read off the collection, so it has to ask for one.

    Without this the column comes back empty with a 200, which is
    indistinguishable from a document that genuinely has no collection.
    """
    stub_engine.add_export_response([_row("doc-1")])

    _download(test_client, columns=["BUNDLE_URL"], base_url="https://example.org")

    assert [request.resolve_collections for request in stub_engine.export_requests] == [True]


def test_download_rejects_a_base_url_that_is_not_a_url(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """
    An unusable `base_url` is refused rather than built into a broken link.

    Without a scheme and host there is nothing to join a slug onto, so every
    URL cell would be a relative path handed back with a 200.
    """
    stub_engine.add_export_response([_row("doc-1", slug="a-document")])

    response = _download(test_client, columns=["URL"], base_url="not-a-url")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_download_rejects_an_empty_base_url(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    stub_engine.add_export_response([_row("doc-1", slug="a-document")])

    response = _download(test_client, columns=["URL"], base_url="")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
