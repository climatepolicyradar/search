from dataclasses import dataclass

from search.engines import ListResponse, OrderBy, Pagination, VespaError
from search.engines.dev_vespa import Filter
from search.label import LabelSearchResult


@dataclass
class AsearchRequest:
    query: str | None
    pagination: Pagination
    order_by: list[OrderBy]
    filters: Filter | None
    label_type: str | None


class StubLabelSearchEngine:
    def __init__(self) -> None:
        self.asearch_requests: list[AsearchRequest] = []
        self.all_labels_calls = 0
        self._asearch_responses: list[ListResponse[LabelSearchResult] | VespaError] = []
        self._all_labels_responses: list[list[LabelSearchResult] | VespaError] = []

    def add_asearch_response(
            self,
            response: ListResponse[LabelSearchResult] | VespaError,
        ) -> None:
        self._asearch_responses.append(response)

    def add_all_labels_response(
            self,
            response: list[LabelSearchResult] | VespaError,
        ) -> None:
        self._all_labels_responses.append(response)

    async def asearch(
            self,
            query: str | None,
            pagination: Pagination,
            order_by: list[OrderBy],
            filters: Filter | None = None,
            label_type: str | None = None,
        ) -> ListResponse[LabelSearchResult]:
        self.asearch_requests.append(
            AsearchRequest(
                query=query,
                pagination=pagination,
                order_by=order_by,
                filters=filters,
                label_type=label_type,
            )
        )
        match self._asearch_responses.pop(0):
            case VespaError() as error:
                raise error
            case response:
                return response

    async def all_labels(self) -> list[LabelSearchResult]:
        self.all_labels_calls += 1
        match self._all_labels_responses.pop(0):
            case VespaError() as error:
                raise error
            case response:
                return response
