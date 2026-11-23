from collections.abc import Generator

from stream.source import Source


class ListSource[A](Source[A]):
    def __init__(self, items: list[A]) -> None:
        self._items = items

    def lines(self) -> Generator[A]:
        """Yield each item in the list."""
        yield from self._items
