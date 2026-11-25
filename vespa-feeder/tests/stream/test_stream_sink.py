from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

import orjson
import pytest
from pydantic import ValidationError
from vespa_feeder.stream.sink import RecordsLost, VespaFeedSummary, VespaSink
from vespa_feeder.stream.stream import Stream


def vespa_summary(operations: int, ok: int) -> bytes:
    return orjson.dumps(
        {
            "feeder.operation.count": operations,
            "feeder.seconds": 1.5,
            "feeder.ok.count": ok,
            "feeder.error.count": 0,
            "http.response.error.count": operations - ok,
            "http.response.code.counts": {"200": ok, "500": operations - ok},
        }
    )


class StandInSink(VespaSink):
    def __init__(self, args: list[str]) -> None:
        super().__init__(
            target="http://localhost",
            application="tenant.app",
            token="token",  # nosec B106
            deployment_name="deployment",
            run_name="run",
        )
        self._args = args

    def vespa_feed_args(self) -> list[str]:
        """Run the given command in place of `vespa feed`."""
        return self._args


def recording_sink(received: Path, operations: int, ok: int) -> StandInSink:
    summary = vespa_summary(operations=operations, ok=ok).decode()
    script = 'cat > "$0"; printf "%s" "$1"'
    return StandInSink(args=["sh", "-c", script, str(received), summary])


def failing_after_one() -> Stream[dict[str, Any]]:
    yield {"id": "a"}
    raise ValueError("upstream broke")


def interrupted_after_one() -> Stream[dict[str, Any]]:
    yield {"id": "a"}
    raise KeyboardInterrupt


def many_documents() -> Stream[dict[str, Any]]:
    for number in range(100_000):
        yield {"id": number}


def test_vespa_sink_writes_each_item_as_a_json_line(tmp_path: Path) -> None:
    received = tmp_path / "received.jsonl"
    sink = recording_sink(received=received, operations=2, ok=2)
    sink.drain(iter([{"id": "a"}, {"id": "b"}]))
    assert received.read_bytes().splitlines() == [b'{"id":"a"}', b'{"id":"b"}']


def test_vespa_sink_feeds_items_sent_before_upstream_failed(tmp_path: Path) -> None:
    received = tmp_path / "received.jsonl"
    sink = recording_sink(received=received, operations=1, ok=1)
    with pytest.raises(ValueError):
        sink.drain(failing_after_one())
    assert received.read_bytes().splitlines() == [b'{"id":"a"}']


def test_vespa_sink_raises_when_records_are_lost(tmp_path: Path) -> None:
    sink = recording_sink(received=tmp_path / "received.jsonl", operations=3, ok=1)
    with pytest.raises(RecordsLost):
        sink.drain(iter([{"id": "a"}]))


def test_vespa_sink_raises_on_a_non_zero_exit() -> None:
    sink = StandInSink(args=["sh", "-c", "cat > /dev/null; exit 3"])
    with pytest.raises(CalledProcessError):
        sink.drain(iter([{"id": "a"}]))


def test_vespa_sink_reports_the_exit_code_when_vespa_stops_reading() -> None:
    sink = StandInSink(args=["sh", "-c", "exit 3"])
    with pytest.raises(CalledProcessError):
        sink.drain(many_documents())


def test_vespa_sink_raises_the_upstream_error_when_vespa_fails_too() -> None:
    sink = StandInSink(args=["sh", "-c", "cat > /dev/null; exit 3"])
    with pytest.raises(ValueError) as raised:
        sink.drain(failing_after_one())
    assert "CalledProcessError" in raised.value.__notes__[0]


def test_vespa_sink_kills_the_process_when_interrupted() -> None:
    sink = StandInSink(args=["sleep", "60"])
    with pytest.raises(KeyboardInterrupt):
        sink.drain(interrupted_after_one())


def test_vespa_feed_summary_keys_response_codes_by_int() -> None:
    summary = VespaFeedSummary.model_validate_json(vespa_summary(operations=3, ok=1))
    assert summary.response_code_counts == {200: 1, 500: 2}


def test_vespa_feed_summary_loses_nothing_when_all_succeed() -> None:
    summary = VespaFeedSummary.model_validate_json(vespa_summary(operations=2, ok=2))
    assert summary.lost == 0


def test_vespa_feed_summary_counts_operations_without_a_200_as_lost() -> None:
    summary = VespaFeedSummary.model_validate_json(vespa_summary(operations=3, ok=1))
    assert summary.lost == 2


def test_vespa_feed_summary_rejects_output_missing_a_field() -> None:
    with pytest.raises(ValidationError):
        VespaFeedSummary.model_validate_json(b'{"feeder.ok.count": 1}')
