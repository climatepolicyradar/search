"""Table-driven tests for the `vespa feed` CLI subprocess the feeder drives."""

import contextlib
import signal
import subprocess

import pytest
import vespa_feeder as feeder
from helpers import (
    _FakeVespaFeed,
    _FakeVespaFeedProcess,
    _vespa_feed_stdout,
    _write_jsonl,
)


@pytest.fixture
def displaced_sigterm_handler():
    """
    Install a no-op SIGTERM handler for the feeder's own handler to displace.

    Both the handler and `_previous_sigterm_handler` are process-wide, so they
    have to be put back afterwards. The no-op also keeps `raise_signal` from
    reaching a default disposition that would kill the test session.
    """
    original = signal.getsignal(signal.SIGTERM)
    original_previous = feeder._main_thread_sigterm_handler

    displaced_signums: list[int] = []
    signal.signal(signal.SIGTERM, lambda signum, _: displaced_signums.append(signum))
    yield displaced_signums

    signal.signal(signal.SIGTERM, original)
    feeder._main_thread_sigterm_handler = original_previous
    feeder._vespa_feed_processes.clear()

def test_feed_derived_files_invokes_the_cli_once_for_the_whole_batch(
    monkeypatch, tmp_path
):
    files = [
        _write_jsonl(tmp_path / f"{n}.jsonl", [{"id": n}, {"id": n + 100}])
        for n in range(3)
    ]
    fake_feed = _FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    result = feeder.feed_derived_files(
        materialised_derived_files=files,
        endpoint="http://vespa",
        application="app",
        feed_timeout_seconds_per_file=300,
    )

    assert len(fake_feed.calls) == 1
    assert fake_feed.calls[0][:2] == ["vespa", "feed"]
    assert fake_feed.calls[0][2:5] == [str(path) for path in files]
    assert fake_feed.timeouts == [900]
    assert result.input_count == 6


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected"),
    [
        pytest.param(
            _vespa_feed_stdout(operation=10, ok=10),
            "",
            {
                "operation_count": 10,
                "ok_count": 10,
                "feeder_error_count": 0,
                "throttled_count": 0,
                "other_http_error_count": 0,
                "errors": [],
            },
            id="everything-indexed",
        ),
        pytest.param(
            _vespa_feed_stdout(operation=10, ok=10, code_counts={"200": 10, "429": 4}),
            "",
            {
                "operation_count": 10,
                "ok_count": 10,
                "feeder_error_count": 0,
                "throttled_count": 4,
                "other_http_error_count": 0,
                "errors": [],
            },
            id="throttling-the-retries-recovered-is-not-a-failure",
        ),
        pytest.param(
            _vespa_feed_stdout(
                operation=10, ok=8, code_counts={"200": 8, "429": 5, "503": 2}
            ),
            "feed: 503 Service Unavailable for put id:doc:doc::9: giving up\n",
            {
                "operation_count": 10,
                "ok_count": 8,
                "feeder_error_count": 0,
                "throttled_count": 5,
                "other_http_error_count": 2,
                "errors": [
                    feeder.VespaResponseError(
                        ok_count=8,
                        operation_count=10,
                        throttled_count=5,
                        other_http_error_count=2,
                        failed_documents=[
                            feeder.FailedDocument(
                                doc_id="id:doc:doc::9", error="503 Service Unavailable"
                            )
                        ],
                    )
                ],
            },
            id="records-lost-after-retries",
        ),
        pytest.param(
            _vespa_feed_stdout(
                operation=10, ok=7, code_counts={"200": 7}, feeder_error_count=3
            ),
            "",
            {
                "operation_count": 10,
                "ok_count": 7,
                "feeder_error_count": 3,
                "throttled_count": 0,
                "other_http_error_count": 0,
                "errors": [
                    feeder.VespaFeedError(feeder_error_count=3, failed_documents=[]),
                    feeder.VespaResponseError(
                        ok_count=7,
                        operation_count=10,
                        throttled_count=0,
                        other_http_error_count=0,
                        failed_documents=[],
                    ),
                ],
            },
            id="transport-gave-up-before-any-response",
        ),
    ],
)
def test_feed_derived_files_reports_what_the_cli_returned(
    monkeypatch, tmp_path, stdout, stderr, expected
):
    files = [_write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    monkeypatch.setattr(feeder.subprocess, "Popen", _FakeVespaFeed(stdout, stderr))

    result = feeder.feed_derived_files(
        materialised_derived_files=files, endpoint="http://vespa", application="app"
    )

    assert {
        "operation_count": result.operation_count,
        "ok_count": result.ok_count,
        "feeder_error_count": result.feeder_error_count,
        "throttled_count": result.throttled_count,
        "other_http_error_count": result.other_http_error_count,
        "errors": result.errors,
    } == expected


def test_feed_derived_files_raises_when_the_cli_exits_non_zero(monkeypatch, tmp_path):
    """A non-zero exit must surface, not be read as a feed that indexed nothing."""
    files = [_write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    monkeypatch.setattr(
        feeder.subprocess,
        "Popen",
        _FakeVespaFeed(
            stderr="dial tcp 127.0.0.1:1: connect: connection refused\n", returncode=1
        ),
    )

    with pytest.raises(subprocess.CalledProcessError):
        feeder.feed_derived_files(
            materialised_derived_files=files,
            endpoint="http://127.0.0.1:1",
            application="app",
        )

def _time_out(process: _FakeVespaFeedProcess) -> None:
    raise subprocess.TimeoutExpired(process.args, timeout=300)


def _sigterm(_: _FakeVespaFeedProcess) -> None:
    signal.raise_signal(signal.SIGTERM)


@pytest.mark.parametrize(
    (
        "mid_feed",
        "returncode",
        "expected_exception",
        "expected_cleanup",
        "expected_forwarded",
    ),
    [
        pytest.param(None, 0, None, None, [], id="feed-succeeded"),
        pytest.param(
            None,
            1,
            subprocess.CalledProcessError,
            None,
            [],
            id="feed-exited-non-zero",
        ),
        pytest.param(
            _time_out, 0, subprocess.TimeoutExpired, "killed", [], id="feed-timed-out"
        ),
        pytest.param(
            _sigterm,
            -signal.SIGTERM,
            subprocess.CalledProcessError,
            "terminated",
            [signal.SIGTERM],
            id="sigterm-mid-feed",
        ),
    ],
)
def test_feed_derived_files_manages_the_vespa_feed_process(
    monkeypatch,
    tmp_path,
    displaced_sigterm_handler,
    mid_feed,
    returncode,
    expected_exception,
    expected_cleanup,
    expected_forwarded,
):
    """
    However the feed ends, it must leave no `vespa feed` behind it.

    Two invariants hold on every row. The process is in
    `_vespa_feed_processes` for exactly as long as it is in flight - left
    behind, some later SIGTERM terminates it long after its batch finished -
    and nothing is still running once the call returns.

    `expected_cleanup` names who had to end the process: nothing on a clean
    exit, `killed` on a timeout (`subprocess.run` used to do that for us),
    `terminated` when the SIGTERM handler reached it.

    `expected_forwarded` is the signal handed back to the one we displaced.
    Under a flow run that is Prefect's SIGTERM bridge, which raises
    TerminationSignal and drives the run to Cancelled; swallowing it leaves
    the flow submitting batches after a graceful stop was asked for.
    """
    files = [_write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    registered_while_in_flight: list[set] = []

    def on_communicate(process: _FakeVespaFeedProcess) -> None:
        registered_while_in_flight.append(set(feeder._vespa_feed_processes))
        if mid_feed is not None:
            mid_feed(process)

    fake_feed = _FakeVespaFeed(returncode=returncode, on_communicate=on_communicate)
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    feeder._terminate_vespa_feed_processes_on_sigterm_handler()
    assert signal.getsignal(signal.SIGTERM) is feeder._terminate_vespa_feed_processes

    raises = (
        contextlib.nullcontext()
        if expected_exception is None
        else pytest.raises(expected_exception)
    )
    with raises:
        feeder.feed_derived_files(
            materialised_derived_files=files,
            endpoint="http://vespa",
            application="app",
        )

    process = fake_feed.processes[0]
    assert registered_while_in_flight == [{process}]
    assert feeder._vespa_feed_processes == set()
    assert process.killed is (expected_cleanup == "killed")
    assert process.terminated is (expected_cleanup == "terminated")
    assert displaced_sigterm_handler == expected_forwarded
