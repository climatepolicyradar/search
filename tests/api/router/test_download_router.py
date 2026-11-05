"""Tests for `GET /search/documents:download`."""

from http import HTTPStatus

import httpx2
from fastapi.testclient import TestClient

from search.data_in_models import (
    Document,
    DocumentRelationship,
    DocumentWithoutRelationships,
)
from search.engines import ListResponse
from search.engines.dev_vespa.documents_search_engine import CollectionReference
from tests.engines.dev_vespa.stub_documents_search_engine import (
    StubDocumentSearchEngine,
)


def _document(id: str, title: str = "t", description: str | None = None) -> Document:
    return Document(id=id, title=title, description=description)


def _download(
        test_client: TestClient,
        query: str = "toxic",
        columns: list[str] | None = None,
        max_results: int | None = None,
        msm: float | None = None,
    ) -> httpx2.Response:
    params: list[tuple[str, str]] = [("query", query)]
    if columns is not None:
        params.extend(("columns", column) for column in columns)
    if max_results is not None:
        params.append(("max_results", str(max_results)))
    if msm is not None:
        params.append(("msm", str(msm)))
    return test_client.get("/search/documents:download", params=tuple(params))


def test_download_returns_csv_with_content_disposition(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:

    stub_engine.add_asearch_response(
        ListResponse(
            results=[_document("doc-1", "A Climate Document")],
            next_page_token=None,
            total_size=1,
        )
    )
    stub_engine.add_collection_references_response({})

    response = _download(test_client)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "doc-1" in response.text


def test_download_defaults_max_results_to_500(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:
    """
    Omitting `max_results` caps the download at 500 rows.

    The cap is asserted through the pages requested, since that is what
    the endpoint does with it: 500 rows at 100 per page is 5 pages, each
    asking for its own 100. Asserting one page's size alone would hold
    for any default at all.
    """
    for _ in range(5):
        stub_engine.add_asearch_response(
            ListResponse(
                results=[_document(f"doc-{i}") for i in range(100)],
                next_page_token=None,
                total_size=500,
            )
        )
        stub_engine.add_collection_references_response({})

    response = _download(test_client)

    assert response.status_code == HTTPStatus.OK
    page_sizes = [request.pagination.page_size for request in stub_engine.asearch_requests]
    assert page_sizes == [100] * 5


def test_download_respects_max_results_query_param(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:
    stub_engine.add_asearch_response(
        ListResponse(
            results=[_document(f"doc-{i}") for i in range(5)],
            next_page_token=None,
            total_size=5,
        )
    )
    stub_engine.add_collection_references_response({})

    response = _download(test_client, max_results=5)

    assert stub_engine.asearch_requests[0].pagination.page_size == 100
    body_rows = response.text.strip().splitlines()[1:]
    assert len(body_rows) == 5


def test_download_pages_without_overlap_when_max_results_is_not_a_whole_page(
        stub_engine: StubDocumentSearchEngine,
        test_client: TestClient,
    ) -> None:
    """
    A `max_results` that is not a multiple of the page size still pages cleanly.

    The engine derives its offset as `(page_token - 1) * page_size`, so a page
    size shrunk to fit the remainder would rewind the offset: at 150 a second
    page of 50 would start at 50, re-emitting rows already written and never
    reaching 100-149. The page size stays fixed and the last page is truncated.
    """
    for page in range(2):
        stub_engine.add_asearch_response(
            ListResponse(
                results=[_document(f"doc-{i}") for i in range(page * 100, page * 100 + 100)],
                next_page_token=None,
                total_size=200,
            )
        )

    response = _download(test_client, max_results=150)

    page_sizes = [request.pagination.page_size for request in stub_engine.asearch_requests]
    assert page_sizes == [100, 100]
    body_rows = response.text.strip().splitlines()[1:]
    assert len(body_rows) == 150
    assert len(set(body_rows)) == 150
    assert body_rows[-1].startswith("doc-149,")


def test_download_rejects_non_positive_max_results(test_client: TestClient) -> None:
    assert _download(test_client, max_results=0).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_download_rejects_out_of_range_msm(test_client: TestClient) -> None:
    assert _download(test_client, msm=1.1).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_download_emits_the_requested_columns_in_order(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """The caller names the columns and their order; the API supplies them."""
    stub_engine.add_asearch_response(
        ListResponse(
            results=[_document("doc-1", "A Climate Document")],
            next_page_token=None,
            total_size=1,
        )
    )
    stub_engine.add_collection_references_response({})

    response = _download(test_client, columns=["TITLE", "ID"])

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[0] == "TITLE,ID"


def test_download_without_columns_still_returns_a_csv(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    """`columns` is optional, so an ad-hoc caller gets a usable CSV."""
    stub_engine.add_asearch_response(
        ListResponse(
            results=[_document("doc-1", "A Climate Document")],
            next_page_token=None,
            total_size=1,
        )
    )
    stub_engine.add_collection_references_response({})

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


def test_download_resolves_collection_reference_for_a_member_of_document(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    document = Document(
        id="doc-1",
        title="A Climate Document",
        documents=[
            DocumentRelationship(
                type="member_of",
                value=DocumentWithoutRelationships(id="collection-1", title="c"),
            )
        ],
    )
    stub_engine.add_asearch_response(
        ListResponse(
            next_page_token=None,
            results=[document],
            total_size=1,
        )
    )
    stub_engine.add_collection_references_response(
        {"collection-1": CollectionReference(id="collection-1", title="A Collection", description="About it")}
    )

    response = _download(
        test_client,
        columns=["ID", "COLLECTION_TITLE", "COLLECTION_DESCRIPTION"],
    )

    assert response.status_code == HTTPStatus.OK
    assert response.text.splitlines()[1] == "doc-1,A Collection,About it"
    assert stub_engine.collection_references_requests == [["collection-1"]]


def test_download_leaves_collection_columns_blank_without_a_relationship(
        test_client: TestClient,
        stub_engine: StubDocumentSearchEngine,
    ) -> None:
    stub_engine.add_asearch_response(
        ListResponse(
            results=[_document("doc-1", "A Climate Document")],
            next_page_token=None,
            total_size=1,
        )
    )
    response = _download(test_client, columns=["ID", "COLLECTION_TITLE"])
    assert response.status_code == HTTPStatus.OK

    assert response.text.splitlines()[1] == "doc-1,"
    assert stub_engine.collection_references_requests == []
