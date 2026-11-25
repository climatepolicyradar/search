from vespa_feeder.stream.stream import Source, Stream


class ListSource[A](Source[A]):
    def __init__(self, items: list[A]) -> None:
        self._items = items

    def lines(self) -> Stream[A]:
        """Yield each item in the list."""
        yield from self._items
