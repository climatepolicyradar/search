from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from httpx2 import Client

from relevance.api.models import (
    DocumentsRequest,
    FilteredSearchRequest,
    PassagesWithinRequest,
    SearchRequest,
    SearchResponse,
)
from search.data_in_models import Document
from search.label import LabelSearchResult
from search.passage import Passage


class SearchClient:

    def __init__(self, client: Client) -> None:
        self._client = client

    @classmethod
    @contextmanager
    def create(cls, url: str | None) -> Generator["SearchClient"]:
        """Create either an external (url) or in process (no URL) client"""
        if url:
            with Client(base_url=url) as client:
                yield cls(client)
        else:
            from api.main import app
            with TestClient(app) as client:
                yield cls(client)

    def _get(self, path: str, request: SearchRequest) -> bytes:
        params = request.model_dump(
            exclude_none=True,
            by_alias=True,
            mode="json",
        )
        params["order_by"] = "relevance desc"
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.content

    def documents(self, request: DocumentsRequest) -> SearchResponse[Document]:
        """Search documents by relevance."""
        content = self._get("/search/documents", request)
        return SearchResponse[Document].model_validate_json(content)

    def labels(self, request: SearchRequest) -> SearchResponse[LabelSearchResult]:
        """Search labels by relevance."""
        content = self._get("/search/labels", request)
        return SearchResponse[LabelSearchResult].model_validate_json(content)

    def passages(self, request: FilteredSearchRequest) -> SearchResponse[Passage]:
        """Search passages by relevance."""
        content = self._get("/search/passages", request)
        return SearchResponse[Passage].model_validate_json(content)

    def passages_within(
        self,
        request: PassagesWithinRequest,
    ) -> SearchResponse[Passage]:
        """Search passages within the given documents by relevance."""
        content = self._get("/search/passages:within", request)
        return SearchResponse[Passage].model_validate_json(content)
