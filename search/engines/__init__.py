from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from knowledge_graph.identifiers import Identifier

from search.document import Document
from search.label import Label
from search.passage import Passage

TModel = TypeVar("TModel", Label, Passage, Document)


class SearchEngine(ABC, Generic[TModel]):
    """Base class for a search engine"""

    model_class: type[TModel]

    @abstractmethod
    def search(self, terms: str) -> list[TModel]:
        """Fetch a list of relevant search results"""

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
    def search(self, terms: str) -> list[Document]:
        """Fetch a list of relevant documents"""


class PassageSearchEngine(SearchEngine[Passage]):
    """A search engine that searches for passages"""

    model_class = Passage

    @abstractmethod
    def search(self, terms: str) -> list[Passage]:
        """Fetch a list of relevant passages"""


class LabelSearchEngine(SearchEngine[Label]):
    """A search engine that searches for labels"""

    model_class = Label

    @abstractmethod
    def search(self, terms: str) -> list[Label]:
        """Fetch a list of relevant labels"""
