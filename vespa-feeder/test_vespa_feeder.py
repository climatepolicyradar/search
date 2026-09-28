"""Table-driven tests for the pieces the v2 feeder flow composes."""

import contextlib
import json
import signal
import subprocess
import tempfile
from collections.abc import Callable
from itertools import takewhile
from pathlib import Path

import orjson
import pytest
import vespa_feeder as feeder


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_bytes(b"".join(orjson.dumps(record) + b"\n" for record in records))
    return path


def _read_jsonl(path: Path) -> list[dict]:
    return [
        orjson.loads(line) for line in path.read_bytes().splitlines() if line.strip()
    ]


def _vespa_feed_stdout(
    operation: int,
    ok: int,
    code_counts: dict[str, int] | None = None,
    feeder_error_count: int = 0,
) -> str:
    """The stats JSON `vespa feed` prints to stdout."""
    code_counts = {"200": ok} if code_counts is None else code_counts
    return json.dumps(
        {
            "feeder.operation.count": operation,
            "feeder.ok.count": ok,
            "feeder.error.count": feeder_error_count,
            "feeder.seconds": 0.5,
            "http.response.error.count": sum(
                count for code, count in code_counts.items() if not code.startswith("2")
            ),
            "http.response.code.counts": code_counts,
        }
    )


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        Path(destination).write_bytes(self.objects[key])


class _FakeVespaFeedProcess:
    """The `subprocess.Popen` a `_FakeVespaFeed` hands back."""

    def __init__(self, feed: "_FakeVespaFeed", argv: list[str], stdout: str) -> None:
        self.args = argv
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._feed = feed
        self._stdout = stdout

    def communicate(self, timeout: int | None = None) -> tuple[str, str]:
        self._feed.timeouts.append(timeout)
        if self._feed.on_communicate is not None:
            self._feed.on_communicate(self)
        self.returncode = self._feed.returncode
        return self._stdout, self._feed.stderr

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def __enter__(self) -> "_FakeVespaFeedProcess":
        return self

    def __exit__(self, *_) -> bool:
        return False


class _FakeVespaFeed:
    """
    Stands in for `subprocess.Popen`, recording what `vespa feed` was handed.

    It reads the feed files off disk when the process is spawned, so
    `fed_records` is proof the files still existed and held records at the
    moment they were fed.

    `on_communicate` runs while the process is live and registered in
    `_vespa_feed_processes` - the only window in which a SIGTERM has anything
    to terminate.
    """

    def __init__(
        self,
        stdout: str | None = None,
        stderr: str = "",
        returncode: int = 0,
        on_communicate: Callable[[_FakeVespaFeedProcess], None] | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.on_communicate = on_communicate
        self.calls: list[list[str]] = []
        self.timeouts: list[int | None] = []
        self.fed_records: list[dict] = []
        self.processes: list[_FakeVespaFeedProcess] = []

    def __call__(self, argv: list[str], **kwargs) -> _FakeVespaFeedProcess:
        self.calls.append(argv)

        feed_paths = takewhile(lambda arg: not arg.startswith("--"), argv[2:])
        records = [record for path in feed_paths for record in _read_jsonl(Path(path))]
        self.fed_records.extend(records)

        stdout = self.stdout or _vespa_feed_stdout(
            operation=len(records), ok=len(records)
        )
        process = _FakeVespaFeedProcess(self, argv, stdout)
        self.processes.append(process)
        return process


@pytest.fixture
def temp_workspace(monkeypatch, tmp_path: Path) -> Path:
    """Point the feeder's `tempfile.gettempdir()` at a per-test directory."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path


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


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("search/vespa/labels_feed_materializer.jsonl", id="nested"),
        pytest.param("one.jsonl", id="bucket-root"),
    ],
)
def test_list_s3_keys_treats_a_jsonl_key_as_the_file_itself(monkeypatch, key):
    def _no_s3(_):
        raise AssertionError("a .jsonl key should not be listed as a prefix")

    monkeypatch.setattr(feeder.boto3, "client", _no_s3)

    assert feeder.list_s3_keys(bucket="bucket", key=key) == [key]


@pytest.mark.parametrize(
    ("s3_objects", "batched_s3_keys", "expected_files"),
    [
        pytest.param(
            {"prefix/one.jsonl": b'{"id": 1}\n'},
            ["prefix/one.jsonl"],
            {"one.jsonl": [{"id": 1}]},
            id="one-key",
        ),
        pytest.param(
            {
                "prefix/one.jsonl": b'{"id": 1}\n',
                "prefix/two.jsonl": b'{"id": 2}\n{"id": 3}\n',
            },
            ["prefix/one.jsonl", "prefix/two.jsonl"],
            {"one.jsonl": [{"id": 1}], "two.jsonl": [{"id": 2}, {"id": 3}]},
            id="one-file-per-key",
        ),
        pytest.param(
            {"a/deep/prefix/one.jsonl": b'{"id": 1}\n'},
            ["a/deep/prefix/one.jsonl"],
            {"one.jsonl": [{"id": 1}]},
            id="named-after-the-key-basename",
        ),
        pytest.param({}, [], {}, id="no-keys"),
    ],
)
def test_materialise_s3_files_writes_one_file_per_key(
    monkeypatch, tmp_path, s3_objects, batched_s3_keys, expected_files
):
    monkeypatch.setattr(feeder.boto3, "client", lambda _: _FakeS3(s3_objects))

    paths = feeder.materialise_s3_files(
        bucket="bucket", batched_s3_keys=batched_s3_keys, materialise_dir=tmp_path
    )

    assert paths == [tmp_path / name for name in expected_files]
    assert {path.name: _read_jsonl(path) for path in paths} == expected_files


@pytest.mark.parametrize(
    ("sources", "derive_data_from_source", "expected_files"),
    [
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n{"id": 2}\n'},
            None,
            {"one.derived.jsonl": [{"id": 1}, {"id": 2}]},
            id="no-deriver",
        ),
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n{"id": 2}\n'},
            lambda record: record | {"derived": True},
            {
                "one.derived.jsonl": [
                    {"id": 1, "derived": True},
                    {"id": 2, "derived": True},
                ]
            },
            id="deriver-applied-to-every-record",
        ),
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n\n\n{"id": 2}\n'},
            None,
            {"one.derived.jsonl": [{"id": 1}, {"id": 2}]},
            id="blank-lines-skipped",
        ),
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n', "two.jsonl": b'{"id": 2}\n'},
            None,
            {"one.derived.jsonl": [{"id": 1}], "two.derived.jsonl": [{"id": 2}]},
            id="one-derived-file-per-source",
        ),
        pytest.param(
            {"one.jsonl": b""}, None, {"one.derived.jsonl": []}, id="empty-source"
        ),
    ],
)
def test_materialise_derived_files_writes_a_new_file_per_source(
    tmp_path, sources, derive_data_from_source, expected_files
):
    """
    Every case must leave the sources on disk and untouched.

    `feed_batch` deletes the sources the moment this returns, so handing them
    back instead of new files would delete the files about to be fed.
    """
    source_paths = []
    for name, content in sources.items():
        source_path = tmp_path / name
        source_path.write_bytes(content)
        source_paths.append(source_path)

    derived = feeder.materialise_derived_files(
        materialised_s3_files=source_paths,
        derive_data_from_source=derive_data_from_source,
    )

    assert derived == [tmp_path / name for name in expected_files]
    assert {path.name: _read_jsonl(path) for path in derived} == expected_files
    assert {path.name: path.read_bytes() for path in source_paths} == sources


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


@pytest.mark.parametrize(
    ("present", "absent"),
    [
        pytest.param(["one.jsonl"], [], id="present"),
        pytest.param([], ["gone.jsonl"], id="already-missing"),
        pytest.param(["one.jsonl", "two.jsonl"], ["gone.jsonl"], id="mixed"),
        pytest.param([], [], id="nothing-to-delete"),
    ],
)
def test_delete_materialised_s3_files_removes_every_file_it_is_given(
    tmp_path, present, absent
):
    paths = [_write_jsonl(tmp_path / name, [{"id": 1}]) for name in present]
    paths += [tmp_path / name for name in absent]

    feeder.delete_materialised_s3_files(paths)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("s3_objects", "batched_s3_keys", "derive_data_from_source", "expected_records"),
    [
        pytest.param(
            {"prefix/one.jsonl": b'{"id": 1}\n{"id": 2}\n'},
            ("prefix/one.jsonl",),
            None,
            [{"id": 1}, {"id": 2}],
            id="no-deriver",
        ),
        pytest.param(
            {"prefix/one.jsonl": b'{"id": 1}\n{"id": 2}\n'},
            ("prefix/one.jsonl",),
            lambda record: record | {"derived": True},
            [{"id": 1, "derived": True}, {"id": 2, "derived": True}],
            id="with-deriver",
        ),
        pytest.param(
            {
                "prefix/one.jsonl": b'{"id": 1}\n',
                "prefix/two.jsonl": b'{"id": 2}\n',
            },
            ("prefix/one.jsonl", "prefix/two.jsonl"),
            None,
            [{"id": 1}, {"id": 2}],
            id="whole-batch-in-one-feed",
        ),
    ],
)
def test_feed_batch_feeds_the_records_then_leaves_nothing_on_disk(
    monkeypatch,
    temp_workspace,
    s3_objects,
    batched_s3_keys,
    derive_data_from_source,
    expected_records,
):
    monkeypatch.setattr(feeder.boto3, "client", lambda _: _FakeS3(s3_objects))
    fake_feed = _FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    result = feeder.feed_batch.fn(
        endpoint="http://vespa",
        application="app",
        connections=2,
        feed_timeout_seconds_per_file=300,
        s3_bucket="bucket",
        batched_s3_keys=batched_s3_keys,
        derive_data_from_source=derive_data_from_source,
    )

    assert len(fake_feed.calls) == 1
    assert fake_feed.fed_records == expected_records
    assert result.ok_count == len(expected_records)
    assert result.errors == []
    assert list(temp_workspace.iterdir()) == []


_BATCH_S3_OBJECTS = {
    "prefix/one.jsonl": b'{"id": 1}\n',
    "prefix/two.jsonl": b'{"id": 2}\n',
}


class _BrokenS3(_FakeS3):
    """Downloads every key but the last, leaving a partial batch on disk."""

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        if key == list(self.objects)[-1]:
            raise RuntimeError("s3 download failed")
        super().download_file(bucket, key, destination)


def _broken_deriver(record: dict) -> dict:
    raise RuntimeError("deriver failed")


@pytest.mark.parametrize(
    ("s3_client", "derive_data_from_source", "vespa_feed", "expected_exception"),
    [
        pytest.param(
            lambda: _BrokenS3(_BATCH_S3_OBJECTS),
            None,
            _FakeVespaFeed,
            RuntimeError,
            id="a-download-fails",
        ),
        pytest.param(
            lambda: _FakeS3(_BATCH_S3_OBJECTS),
            _broken_deriver,
            _FakeVespaFeed,
            RuntimeError,
            id="the-deriver-raises",
        ),
        pytest.param(
            lambda: _FakeS3(_BATCH_S3_OBJECTS),
            None,
            lambda: _FakeVespaFeed(returncode=1),
            subprocess.CalledProcessError,
            id="vespa-feed-exits-non-zero",
        ),
    ],
)
def test_feed_batch_leaves_nothing_on_disk_when_it_fails(
    monkeypatch,
    temp_workspace,
    s3_client,
    derive_data_from_source,
    vespa_feed,
    expected_exception,
):
    """
    The failure has to reach the caller with no file left behind.

    Both halves matter: the batch runs on a long-lived worker, so a leak here
    accumulates across every batch of the run, and swallowing the error would
    report a batch as fed that never was.
    """
    monkeypatch.setattr(feeder.boto3, "client", lambda _: s3_client())
    monkeypatch.setattr(feeder.subprocess, "Popen", vespa_feed())

    with pytest.raises(expected_exception):
        feeder.feed_batch.fn(
            endpoint="http://vespa",
            application="app",
            connections=2,
            feed_timeout_seconds_per_file=300,
            s3_bucket="bucket",
            batched_s3_keys=tuple(_BATCH_S3_OBJECTS),
            derive_data_from_source=derive_data_from_source,
        )

    assert list(temp_workspace.iterdir()) == []
