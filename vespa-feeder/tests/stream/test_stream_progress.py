import logging

import pytest
from pydantic import ValidationError
from vespa_feeder.stream.progress import IncompleteStats, VespaFeedStats, parse_stats
from vespa_feeder.stream.stream import Stream

from tests.stream.vespa_stats import vespa_stats, vespa_stats_json


def chunks(parts: list[bytes]) -> Stream[bytes]:
    yield from parts


def test_parse_stats_yields_a_printed_snapshot() -> None:
    output = chunks(parts=[vespa_stats_json(operations=3, ok=3)])
    assert list(parse_stats(output)) == [vespa_stats(operations=3, ok=3)]


def test_parse_stats_joins_a_snapshot_split_across_chunks() -> None:
    snapshot = vespa_stats_json(operations=3, ok=3)
    output = chunks(parts=[snapshot[:40], b"", snapshot[40:]])
    assert list(parse_stats(output)) == [vespa_stats(operations=3, ok=3)]


def test_parse_stats_yields_every_snapshot() -> None:
    first = vespa_stats_json(operations=1, ok=1)
    second = vespa_stats_json(operations=2, ok=2)
    stats = list(parse_stats(chunks(parts=[first + second])))
    assert [snapshot.operation_count for snapshot in stats] == [1, 2]


def test_parse_stats_reads_a_snapshot_with_no_final_newline() -> None:
    output = chunks(parts=[vespa_stats_json(operations=3, ok=3).rstrip()])
    assert list(parse_stats(output)) == [vespa_stats(operations=3, ok=3)]


def test_parse_stats_logs_each_snapshot(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    list(parse_stats(chunks(parts=[vespa_stats_json(operations=6, ok=3)])))
    assert caplog.messages == ["vespa feed: 6 fed, 2 ok/s, 0 skipped/s, 0 errors"]


def test_describe_reports_skipped_updates_separately() -> None:
    stats = vespa_stats(operations=3, ok=1).model_copy(update={"response_codes": {200: 1, 412: 2}})
    assert stats.describe() == "3 fed, 1 ok/s, 1 skipped/s, 0 errors"


def test_parse_stats_raises_when_output_ends_inside_a_snapshot() -> None:
    output = chunks(parts=[vespa_stats_json(operations=3, ok=3)[:40]])
    with pytest.raises(IncompleteStats):
        list(parse_stats(output))


def test_parse_stats_logs_lines_outside_a_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    snapshot = vespa_stats_json(operations=3, ok=3)
    output = chunks(parts=[b"feed: got error\n" + snapshot])
    assert list(parse_stats(output)) == [vespa_stats(operations=3, ok=3)]
    assert caplog.messages == ["vespa feed: feed: got error"]


def test_vespa_feed_stats_keys_response_codes_by_int() -> None:
    assert vespa_stats(operations=3, ok=1).response_codes == {200: 1, 500: 2}


def test_vespa_feed_stats_rejects_output_missing_a_field() -> None:
    with pytest.raises(ValidationError):
        VespaFeedStats.model_validate_json(b'{"feeder.ok.count": 1}')


def test_vespa_feed_stats_since_subtracts_the_earlier_counts() -> None:
    change = vespa_stats(operations=10, ok=7).since(vespa_stats(operations=4, ok=3))
    assert change.operation_count == 6
    assert change.ok_count == 4
    assert change.response_codes == {200: 4, 500: 2}


def test_vespa_feed_stats_since_empty_is_unchanged() -> None:
    stats = vespa_stats(operations=10, ok=7)
    assert stats.since(VespaFeedStats.empty()) == stats
