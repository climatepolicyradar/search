from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from knowledge_graph.identifiers import Identifier

from search.data_in_models import Document as DocumentModel
from search.data_in_models import Label as LabelModel
from search.document import Document
from search.label import Label
from search.passage import Passage

TModel = TypeVar("TModel", Label, Passage, Document, DocumentModel, LabelModel)


class SearchEngine(ABC, Generic[TModel]):
    """Base class for a search engine"""

    model_class: type[TModel]

    @abstractmethod
    def search(
        self,
        query: str,
        filters_json_string: str | None,
        page_token: int,
        page_size: int = 0,
    ) -> list[TModel]:
        """
        Fetch a list of relevant search results.

        :param query: Search query to match against
        :param filters_json_string: JSON string of AND/OR filters
        :param limit: Maximum number of results to return
        :param offset: Number of results to skip (for pagination)
        :return: List of matching items
        """

    @abstractmethod
    def count(self, query: str) -> int:
        """
        Count total number of results matching the search query.

        More efficient than len(search(query)) for database-backed engines.

        :param terms: Search terms to match against
        :return: Total count of matching items
        """

    def __repr__(self) -> str:
        """Return a string representation of the search engine"""
        return f"{self.name} ({self.model_class.__name__})"

    @property
    def name(self) -> str:
        """Return the name of the search engine"""
        return self.__class__.__name__

    @property
    def id(self) -> Identifier:
        """Canonical ID for search engine"""

        return Identifier.generate(
            str(self),
        )
