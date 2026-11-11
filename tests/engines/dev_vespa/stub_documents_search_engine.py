from dataclasses import dataclass

from search.data_in_models import Document
from search.engines import ListResponse, OrderBy, Pagination, VespaError
from search.engines.dev_vespa import Filter
from search.engines.dev_vespa.documents_search_engine import (
    CollectionReference,
    ExportRow,
)


@dataclass
class AsearchRequest:
    query: str | None
    pagination: Pagination
    order_by: list[OrderBy]
    filters: Filter | None


@dataclass
class ExportRequest:
    query: str | None
    limit: int
    order_by: list[OrderBy]
    filters: Filter | None
    resolve_collections: bool


class StubDocumentSearchEngine:
    def __init__(self) -> None:
        self.asearch_requests: list[AsearchRequest] = []
        self.collection_references_requests: list[list[str]] = []
        self._asearch_responses: list[ListResponse[Document] | VespaError] = []
        self._collection_references_responses: list[dict[str, CollectionReference] | VespaError] = []
        self.export_requests: list[ExportRequest] = []
        self._export_responses: list[list[ExportRow] | VespaError] = []

    def add_asearch_response(self, response: ListResponse[Document] | VespaError) -> None:
        self._asearch_responses.append(response)

    def add_collection_references_response(
            self,
            response: dict[str, CollectionReference] | VespaError,
        ) -> None:
        self._collection_references_responses.append(response)

    def add_export_response(self, response: list[ExportRow] | VespaError) -> None:
        self._export_responses.append(response)

    async def export(
            self,
            query: str | None,
            limit: int,
            order_by: list[OrderBy],
            filters: Filter | None = None,
            resolve_collections: bool = True,
        ) -> list[ExportRow]:
        self.export_requests.append(
            ExportRequest(
                query=query,
                limit=limit,
                order_by=order_by,
                filters=filters,
                resolve_collections=resolve_collections,
            )
        )
        match self._export_responses.pop(0):
            case VespaError() as error:
                raise error
            case response:
                return response

    async def asearch(
            self,
            query: str | None,
            pagination: Pagination,
            order_by: list[OrderBy],
            filters: Filter | None = None,
        ) -> ListResponse[Document]:
        self.asearch_requests.append(
            AsearchRequest(
                query=query,
                pagination=pagination,
                order_by=order_by,
                filters=filters,
            )
        )
        match self._asearch_responses.pop(0):
            case VespaError() as error:
                raise error
            case response:
                return response

    async def collection_references(self, document_ids: list[str]) -> dict[str, CollectionReference]:
        self.collection_references_requests.append(document_ids)
        match self._collection_references_responses.pop(0):
            case VespaError() as error:
                raise error
            case response:
                return response
