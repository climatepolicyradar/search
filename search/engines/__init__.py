from abc import ABC, abstractmethod

from search import SearchResult
from search.document import Document
from search.label import Label
from search.passage import Passage


class SearchEngine(ABC):
    """Base class for a search engine"""

    @abstractmethod
    def search(self, terms: str) -> list[SearchResult]:
        """Fetch a list of relevant search results"""


class DocumentSearchEngine(SearchEngine):
    """A search engine that searches for documents"""

    @abstractmethod
    def search(self, terms: str) -> list[Document]:
        """Fetch a list of relevant documents"""


class PassageSearchEngine(SearchEngine):
    """A search engine that searches for passages"""

    @abstractmethod
    def search(self, terms: str) -> list[Passage]:
        """Fetch a list of relevant passages"""


class LabelSearchEngine(SearchEngine):
    """A search engine that searches for labels"""

    @abstractmethod
    def search(self, terms: str) -> list[Label]:
        """Fetch a list of relevant labels"""
