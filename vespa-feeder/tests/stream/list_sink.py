from stream.sink import Sink


class ListSink[A](Sink[A]):
    def __init__(self) -> None:
        self.items: list[A] = []

    def write(self, line: A) -> None:
        """Append the item to `items`."""
        self.items.append(line)
