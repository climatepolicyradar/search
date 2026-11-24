import os
from io import BytesIO

import orjson
import pytest
from pydantic import ValidationError
from vespa_feeder.stream.sink import VespaFeedSummary, VespaSink, VespaStoppedReading


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


def test_vespa_sink_writes_each_document_as_a_json_line() -> None:
    stdin = BytesIO()
    sink = VespaSink(stdin=stdin)
    sink.write({"id": "a"})
    sink.write({"id": "b"})
    assert stdin.getvalue().splitlines() == [b'{"id":"a"}', b'{"id":"b"}']


def test_vespa_sink_reports_vespa_stopped_reading_on_a_broken_pipe() -> None:
    read_end, write_end = os.pipe()
    os.close(read_end)
    with (
        open(write_end, "wb", buffering=0) as stdin,
        pytest.raises(VespaStoppedReading),
    ):
        VespaSink(stdin=stdin).write({"id": "a"})


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
