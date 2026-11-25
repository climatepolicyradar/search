from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from contextlib import closing

type Stream[A] = Generator[A]
type Pipe[A, B] = Callable[[Stream[A]], Stream[B]]
type Sink[A] = Callable[[Stream[A]], None]


class Source[A](ABC):
    @abstractmethod
    def lines(self) -> Stream[A]:
        """Yield every item in the source."""
        ...

    def chain[B](self, pipe: Pipe[A, B]) -> Source[B]:
        """Return a source whose items have passed through the pipe."""
        return Chain(source=self, pipe=pipe)

    def run(self, sink: Sink[A]) -> None:
        """Drain this source into the sink."""
        with closing(self.lines()) as stream:
            sink(stream)


class Chain[A, B](Source[B]):
    def __init__(self, source: Source[A], pipe: Pipe[A, B]) -> None:
        self._source = source
        self._pipe = pipe

    def lines(self) -> Stream[B]:
        """Yield every item of the wrapped source, passed through the pipe."""
        with closing(self._source.lines()) as upstream:
            yield from self._pipe(upstream)
