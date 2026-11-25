import pytest
from vespa_feeder.stream.stream import Source, Stream

from tests.stream.list_source import ListSource


class ClosureRecordingSource(Source[int]):
    def __init__(self) -> None:
        self.closed = False

    def lines(self) -> Stream[int]:
        """Yield two items, recording when the stream is closed."""
        try:
            yield 1
            yield 2
        finally:
            self.closed = True


def failing_after_one(items: Stream[int]) -> None:
    next(items)
    raise ValueError("sink broke")


def doubled(items: Stream[int]) -> Stream[int]:
    for item in items:
        yield item * 2


def described(items: Stream[int]) -> Stream[str]:
    for item in items:
        yield f"item {item}"


def failing_on_two(items: Stream[int]) -> Stream[int]:
    for item in items:
        if item == 2:
            raise ValueError(item)
        yield item


def test_chain_passes_items_through_the_pipe() -> None:
    source = ListSource(items=[1, 2, 3])
    assert list(source.chain(doubled).lines()) == [2, 4, 6]


def test_chained_pipes_apply_in_order() -> None:
    source = ListSource(items=[1, 2])
    assert list(source.chain(doubled).chain(described).lines()) == ["item 2", "item 4"]


def test_run_drains_every_item_into_the_sink() -> None:
    drained: list[int] = []
    ListSource(items=[1, 2, 3]).run(drained.extend)
    assert drained == [1, 2, 3]


def test_run_raises_when_a_pipe_fails_part_way() -> None:
    drained: list[int] = []
    with pytest.raises(ValueError):
        ListSource(items=[1, 2, 3]).chain(failing_on_two).run(drained.extend)


def test_run_closes_the_stream_when_the_sink_fails() -> None:
    source = ClosureRecordingSource()
    with pytest.raises(ValueError) as raised:
        source.run(failing_after_one)
    assert source.closed
    assert raised.type is ValueError
