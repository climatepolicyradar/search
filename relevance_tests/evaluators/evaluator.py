from collections.abc import Sequence
from typing import Protocol


class HasId(Protocol):
    @property
    def id(self) -> str:
        """The result's ID."""
        ...


class HasResults[T](Protocol):
    @property
    def results(self) -> Sequence[T]:
        """The search results, in rank order."""
        ...


class HasTotalSize(Protocol):
    @property
    def total_size(self) -> int | None:
        """The total number of hits, across all pages."""
        ...


class HasSearchPair[T](Protocol):
    @property
    def first(self) -> T:
        """The response to the case's query."""
        ...

    @property
    def second(self) -> T:
        """The response to the query it is compared against."""
        ...
