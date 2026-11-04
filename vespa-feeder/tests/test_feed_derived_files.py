"""Table-driven tests for the `vespa feed` CLI subprocess the feeder drives."""

import contextlib
import signal
import subprocess

import pytest
import vespa_feeder as feeder
from helpers import (
    FakeVespaFeed,
    FakeVespaFeedProcess,
    vespa_feed_stdout,
    write_jsonl,
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
        write_jsonl(tmp_path / f"{n}.jsonl", [{"id": n}, {"id": n + 100}])
        for n in range(3)
    ]
    fake_feed = FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    result = feeder.feed_derived_files(
        materialised_derived_files=files,
        endpoint="http://vespa",
        application="app",
        feed_timeout_seconds=2700,
    )

    assert len(fake_feed.calls) == 1
    assert fake_feed.calls[0][:2] == ["vespa", "feed"]
    assert fake_feed.calls[0][2:5] == [str(path) for path in files]
    assert fake_feed.timeouts == [2700]
    assert result.input_count == 6


@pytest.mark.parametrize("file_count", [1, 3, 10])
def test_feed_derived_files_bounds_the_batch_not_each_file(
    monkeypatch, tmp_path, file_count
):
    """
    The bound is flat per batch, not `per_file * len(files)`.

    Measured over 24h of production runs, file count did not predict duration:
    the worst passages batch (38.7 min) held 10 files, exactly like the 39
    batches in the same run that finished in under 18 minutes. Scaling by it
    also under-bounded the small batches -- a 1-file labels run got 5 minutes
    against work observed to take up to 38.7.
    """
    files = [
        write_jsonl(tmp_path / f"{n}.jsonl", [{"id": n}]) for n in range(file_count)
    ]
    fake_feed = FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    feeder.feed_derived_files(
        materialised_derived_files=files,
        endpoint="http://vespa",
        application="app",
    )

    assert fake_feed.timeouts == [feeder._VESPA_FEED_TIMEOUT_SECONDS]


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected"),
    [
        pytest.param(
            vespa_feed_stdout(operation=10, ok=10),
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
            vespa_feed_stdout(operation=10, ok=10, code_counts={"200": 10, "429": 4}),
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
            vespa_feed_stdout(
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
            vespa_feed_stdout(
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
    files = [write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    monkeypatch.setattr(feeder.subprocess, "Popen", FakeVespaFeed(stdout, stderr))

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
    files = [write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    monkeypatch.setattr(
        feeder.subprocess,
        "Popen",
        FakeVespaFeed(
            stderr="dial tcp 127.0.0.1:1: connect: connection refused\n", returncode=1
        ),
    )

    with pytest.raises(subprocess.CalledProcessError):
        feeder.feed_derived_files(
            materialised_derived_files=files,
            endpoint="http://127.0.0.1:1",
            application="app",
        )


def _time_out(process: FakeVespaFeedProcess) -> None:
    raise subprocess.TimeoutExpired(process.args, timeout=300)


def _sigterm(_: FakeVespaFeedProcess) -> None:
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
    files = [write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    registered_while_in_flight: list[set] = []

    def on_communicate(process: FakeVespaFeedProcess) -> None:
        registered_while_in_flight.append(set(feeder._vespa_feed_processes))
        if mid_feed is not None:
            mid_feed(process)

    fake_feed = FakeVespaFeed(returncode=returncode, on_communicate=on_communicate)
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


def test_feed_derived_files_raises_when_the_feed_outlasts_its_timeout(
    monkeypatch, tmp_path
):
    """
    The bound the feeder passes is enforced, not merely recorded.

    `FakeVespaFeed` honours `communicate`'s timeout the way `Popen` does, so
    this fails if the feeder ever stops passing one.
    """
    files = [write_jsonl(tmp_path / "a.jsonl", [{"id": 1}])]
    fake_feed = FakeVespaFeed(seconds_to_feed=10_000)
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    with pytest.raises(subprocess.TimeoutExpired):
        feeder.feed_derived_files(
            materialised_derived_files=files,
            endpoint="http://vespa",
            application="app",
        )

    assert fake_feed.processes[0].killed is True


def test_feed_derived_files_hands_the_cli_the_whole_invocation(monkeypatch, tmp_path):
    """
    Pin the flags and the `Popen` keywords, not just the files.

    Everything after the file list went unasserted, so a typo in a flag name,
    or a dropped `text=True`, read as success here while breaking the real
    CLI. `text=True` in particular decides whether `communicate` hands back
    `str` or `bytes`, which changes how the JSON and the stderr regex parse.

    `--verbose` is deliberately absent: it logs every successful operation as
    well as every failed one, which cost ~1GB of stderr on a passages run.
    """
    files = [write_jsonl(tmp_path / "a.jsonl", [{"id": 1}])]
    fake_feed = FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    feeder.feed_derived_files(
        materialised_derived_files=files,
        endpoint="http://vespa",
        application="app",
        connections=4,
    )

    assert fake_feed.calls[0] == [
        "vespa",
        "feed",
        str(files[0]),
        "--target",
        "http://vespa",
        "--application",
        "app",
        "--connections",
        "4",
        "--inflight",
        "0",
    ]
    # Dropping either pipe loses the output the feeder parses: stdout carries
    # the JSON summary, stderr the per-document failures.
    assert fake_feed.call_kwargs[0]["stdout"] is subprocess.PIPE
    assert fake_feed.call_kwargs[0]["stderr"] is subprocess.PIPE
    assert fake_feed.call_kwargs[0]["text"] is True
