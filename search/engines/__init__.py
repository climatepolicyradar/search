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
    def search(self, query: str, limit: int, offset: int = 0) -> list[TModel]:
        """
        Fetch a list of relevant search results.

        :param query: Search query to match against
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


class DocumentSearchEngine(SearchEngine[Document]):
    """A search engine that searches for documents"""

    model_class = Document

    @abstractmethod
    def search(
        self, query: str, limit: int | None = None, offset: int = 0
    ) -> list[Document]:
        """
        Fetch a list of relevant documents.

        :param query: Search query to match against
        :param limit: Maximum number of results to return. If None, returns all results.
        :param offset: Number of results to skip (for pagination)
        :return: List of matching documents
        """

    @abstractmethod
    def count(self, query: str) -> int:
        """
        Count total number of documents matching the search query.

        :param query: Search query to match against
        :return: Total count of matching documents
        """


class PassageSearchEngine(SearchEngine[Passage]):
    """A search engine that searches for passages"""

    model_class = Passage

    @abstractmethod
    def search(
        self, query: str, limit: int | None = None, offset: int = 0
    ) -> list[Passage]:
        """
        Fetch a list of relevant passages.

        :param query: Search query to match against
        :param limit: Maximum number of results to return. If None, returns all results.
        :param offset: Number of results to skip (for pagination)
        :return: List of matching passages
        """

    @abstractmethod
    def count(self, query: str) -> int:
        """
        Count total number of passages matching the search query.

        :param query: Search query to match against
        :return: Total count of matching passages
        """


class LabelSearchEngine(SearchEngine[Label]):
    """A search engine that searches for labels"""

    model_class = Label

    @abstractmethod
    def search(
        self, query: str, limit: int | None = None, offset: int = 0
    ) -> list[Label]:
        """
        Fetch a list of relevant labels.

        :param query: Search query to match against
        :param limit: Maximum number of results to return. If None, returns all results.
        :param offset: Number of results to skip (for pagination)
        :return: List of matching labels
        """

    @abstractmethod
    def count(self, query: str) -> int:
        """
        Count total number of labels matching the search query.

        :param query: Search query to match against
        :return: Total count of matching labels
        """
