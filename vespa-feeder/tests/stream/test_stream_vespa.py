import os
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

import pytest
from vespa_feeder.stream.progress import VespaFeedStats, parse_stats
from vespa_feeder.stream.stream import Stream
from vespa_feeder.stream.vespa import VespaFeed

from tests.stream.list_source import ListSource
from tests.stream.vespa_stats import vespa_stats, vespa_stats_json


class StandInFeed(VespaFeed):
    def __init__(self, args: list[str]) -> None:
        super().__init__(
            target="http://localhost",
            application="tenant.app",
            token="token",  # nosec B106
        )
        self._args = args

    def vespa_feed_args(self) -> list[str]:
        """Run the given command in place of `vespa feed`."""
        return self._args


def recording_feed(received: Path, operations: int, ok: int) -> StandInFeed:
    summary = vespa_stats_json(operations=operations, ok=ok).decode()
    script = 'cat > "$0"; printf "%s" "$1"'
    return StandInFeed(args=["sh", "-c", script, str(received), summary])


def documents(ids: list[str]) -> Stream[dict[str, Any]]:
    for document_id in ids:
        yield {"id": document_id}


def failing_after_one() -> Stream[dict[str, Any]]:
    yield {"id": "a"}
    raise ValueError("upstream broke")


def failing_on_first_stats(stats: Stream[VespaFeedStats]) -> None:
    next(stats)
    raise ValueError("sink broke")


def many_documents() -> Stream[dict[str, Any]]:
    for number in range(100_000):
        yield {"id": number}


def test_vespa_feed_writes_each_item_as_a_json_line(tmp_path: Path) -> None:
    received = tmp_path / "received.jsonl"
    feed = recording_feed(received=received, operations=2, ok=2)
    list(feed.feed(documents(ids=["a", "b"])))
    assert received.read_bytes().splitlines() == [b'{"id":"a"}', b'{"id":"b"}']


def test_vespa_feed_yields_the_final_stats(tmp_path: Path) -> None:
    feed = recording_feed(received=tmp_path / "received.jsonl", operations=2, ok=2)
    stats = list(parse_stats(feed.feed(documents(ids=["a", "b"]))))
    assert stats == [vespa_stats(operations=2, ok=2)]


def test_vespa_feed_yields_progress_before_the_final_stats() -> None:
    progress = vespa_stats_json(operations=1, ok=1).decode()
    summary = vespa_stats_json(operations=2, ok=2).decode()
    script = 'printf "%s" "$0" >&2; cat > /dev/null; printf "%s" "$1"'
    feed = StandInFeed(args=["sh", "-c", script, progress, summary])
    stats = list(parse_stats(feed.feed(documents(ids=["a", "b"]))))
    assert [snapshot.operation_count for snapshot in stats] == [1, 2]


def test_vespa_feed_feeds_items_sent_before_upstream_failed(tmp_path: Path) -> None:
    received = tmp_path / "received.jsonl"
    feed = recording_feed(received=received, operations=1, ok=1)
    with pytest.raises(ValueError):
        list(feed.feed(failing_after_one()))
    assert received.read_bytes().splitlines() == [b'{"id":"a"}']


def test_vespa_feed_yields_the_final_stats_before_an_upstream_error(
    tmp_path: Path,
) -> None:
    feed = recording_feed(received=tmp_path / "received.jsonl", operations=1, ok=1)
    stats = parse_stats(feed.feed(failing_after_one()))
    assert next(stats) == vespa_stats(operations=1, ok=1)
    with pytest.raises(ValueError):
        next(stats)


def test_vespa_feed_raises_the_upstream_error_when_vespa_fails_too() -> None:
    feed = StandInFeed(args=["sh", "-c", "cat > /dev/null; exit 3"])
    with pytest.raises(ValueError) as raised:
        list(feed.feed(failing_after_one()))
    assert "CalledProcessError" in raised.value.__notes__[0]


def test_vespa_feed_raises_on_a_non_zero_exit() -> None:
    feed = StandInFeed(args=["sh", "-c", "cat > /dev/null; exit 3"])
    with pytest.raises(CalledProcessError):
        list(feed.feed(documents(ids=["a"])))


def test_vespa_feed_reports_the_exit_code_when_vespa_stops_reading() -> None:
    feed = StandInFeed(args=["sh", "-c", "exit 3"])
    with pytest.raises(CalledProcessError):
        list(feed.feed(many_documents()))


def test_vespa_feed_kills_the_process_when_the_stream_is_closed(tmp_path: Path) -> None:
    exited_normally = tmp_path / "exited-normally"
    script = 'echo started >&2; sleep 3; touch "$0"'
    output = StandInFeed(args=["sh", "-c", script, str(exited_normally)]).feed(
        documents(ids=["a"])
    )
    next(output)
    output.close()
    assert not exited_normally.exists()


def test_vespa_feed_is_killed_when_a_later_stage_fails(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    exited_normally = tmp_path / "exited-normally"
    progress = vespa_stats_json(operations=1, ok=1).decode()
    script = 'echo $$ > "$0"; printf "%s" "$1" >&2; sleep 3; touch "$2"'
    arguments = [str(pid_file), progress, str(exited_normally)]
    feed = StandInFeed(args=["sh", "-c", script, *arguments])
    source = ListSource(items=[{"id": "a"}])
    with pytest.raises(ValueError) as raised:
        source.chain(feed.feed).chain(parse_stats).run(failing_on_first_stats)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    assert not exited_normally.exists()
    assert raised.type is ValueError
