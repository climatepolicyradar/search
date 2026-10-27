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