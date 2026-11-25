from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from contextlib import closing

logger = logging.getLogger(__name__)

# Bounds a hung run inside the 24h gap to the next schedule, so it fails rather
# than queueing tomorrow's run behind it.
RUN_TIMEOUT_SECONDS = 20 * 60 * 60

type Stream[A] = Generator[A]
type Pipe[A, B] = Callable[[Stream[A]], Stream[B]]
type Sink[A] = Callable[[Stream[A]], None]


class TransformFailures(Exception):
    def __init__(self, failures: int) -> None:
        super().__init__(f"{failures} records failed to transform")


def skip_failures[A, B](transform: Callable[[A], B]) -> Pipe[A, B]:
    """Make a pipe that skips items the transform fails on, raising once it ends."""

    def pipe(items: Stream[A]) -> Stream[B]:
        failures = 0
        for item in items:
            try:
                transformed = transform(item)
            except Exception as error:
                logger.warning(f"{transform.__name__} failed on a record", exc_info=True)
                failures += 1
                if failures > 500:
                    raise TransformFailures(failures) from error
                continue
            yield transformed

        if failures > 0:
            raise TransformFailures(failures)

    return pipe


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
