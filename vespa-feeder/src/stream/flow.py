from stream.sink import Sink
from stream.source import Source


class Flow[A]:
    def __init__(self, source: Source[A], sink: Sink[A]) -> None:
        self._source = source
        self._sink = sink

    def transform(self, stream_item: A) -> A:
        """Transform one item on its way from source to sink."""
        return stream_item

    def run(self) -> None:
        """Stream every item from the source, transformed, into the sink."""
        for item in self._source.lines():
            self._sink.write(self.transform(item))
