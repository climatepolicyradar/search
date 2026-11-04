"""Table-driven tests for the pieces the v2 feeder flow composes."""

import contextlib
import json
import logging
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


class _FakeS3CommonPrefixes:
    """An S3 client whose `list_objects_v2` paginator yields `CommonPrefixes`."""

    def __init__(self, pages: list[list[str]]) -> None:
        self.pages = pages
        self.paginate_kwargs: dict = {}

    def get_paginator(self, operation_name: str) -> "_FakeS3CommonPrefixes":
        assert operation_name == "list_objects_v2"
        return self

    def paginate(self, **kwargs) -> list[dict]:
        self.paginate_kwargs = kwargs
        return [
            {
                "CommonPrefixes": [
                    {"Prefix": f"{kwargs['Prefix']}{name}"} for name in page
                ]
            }
            for page in self.pages
        ]


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        pytest.param(
            [["20260922T190625Z/", "20260923T190625Z/"]],
            "20260923T190625Z",
            id="newest-of-two",
        ),
        pytest.param(
            [["20260923T190625Z/", "20260922T190625Z/"]],
            "20260923T190625Z",
            id="listing-order-does-not-matter",
        ),
        pytest.param(
            [["20260924T003000Z/", "20260924T010000Z/"]],
            "20260924T010000Z",
            id="same-day-later-time",
        ),
        pytest.param(
            [["20260923T190625Z/", "latest/"]],
            "20260923T190625Z",
            id="ignores-latest",
        ),
        pytest.param(
            [["20260923T190625Z/"], ["20260924T010000Z/"]],
            "20260924T010000Z",
            id="across-pages",
        ),
    ],
)
def test_get_latest_s3_export_prefix_returns_the_newest_timestamped_prefix(
    monkeypatch, pages, expected
):
    s3 = _FakeS3CommonPrefixes(pages)
    monkeypatch.setattr(feeder.boto3, "client", lambda _: s3)

    assert (
        feeder.get_latest_s3_export_prefix(bucket="bucket", prefix="a/prefix/")
        == expected
    )
    # Delimiter is what keeps this to the prefix names rather than every
    # object beneath them.
    assert s3.paginate_kwargs == {
        "Bucket": "bucket",
        "Prefix": "a/prefix/",
        "Delimiter": "/",
    }


@pytest.mark.parametrize(
    "pages",
    [
        pytest.param([], id="no-pages"),
        pytest.param([[]], id="empty-page"),
        pytest.param([["latest/"]], id="only-latest"),
        pytest.param([["not-a-timestamp/"]], id="unrecognised-prefix"),
        pytest.param([["20260923T190625/"]], id="timestamp-missing-the-z"),
    ],
)
def test_get_latest_s3_export_prefix_raises_when_there_is_no_timestamped_prefix(
    monkeypatch, pages
):
    monkeypatch.setattr(feeder.boto3, "client", lambda _: _FakeS3CommonPrefixes(pages))

    with pytest.raises(FileNotFoundError, match="No timestamped snapshots"):
        feeder.get_latest_s3_export_prefix(bucket="bucket", prefix="a/prefix/")


class _FakeS3Contents:
    """An S3 client whose `list_objects_v2` paginator yields `Contents`."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        self.paginate_kwargs: dict = {}

    def get_paginator(self, operation_name: str) -> "_FakeS3Contents":
        assert operation_name == "list_objects_v2"
        return self

    def paginate(self, **kwargs) -> list[dict]:
        self.paginate_kwargs = kwargs
        prefix = kwargs["Prefix"]
        return [{"Contents": [{"Key": k} for k in self.keys if k.startswith(prefix)]}]


@pytest.mark.parametrize(
    ("keys", "prefix", "expected"),
    [
        pytest.param(
            ["export/20260929T010000Z/b.jsonl", "export/20260929T010000Z/a.jsonl"],
            "export/20260929T010000Z",
            ["export/20260929T010000Z/a.jsonl", "export/20260929T010000Z/b.jsonl"],
            id="prefix-is-a-directory-sorted",
        ),
        pytest.param(
            [
                "export/20260929T010000Z/a.jsonl",
                "export/20260929T010000Z-retry/b.jsonl",
            ],
            "export/20260929T010000Z",
            ["export/20260929T010000Z/a.jsonl"],
            id="sibling-sharing-the-string-prefix-is-excluded",
        ),
    ],
)
def test_list_s3_keys(monkeypatch, keys, prefix, expected):
    monkeypatch.setattr(feeder.boto3, "client", lambda _: _FakeS3Contents(keys))

    assert feeder.list_s3_keys(bucket="bucket", prefix=prefix) == expected


def test_list_s3_keys_raises_when_the_prefix_is_empty(monkeypatch):
    monkeypatch.setattr(feeder.boto3, "client", lambda _: _FakeS3Contents([]))

    with pytest.raises(FileNotFoundError, match="No objects found"):
        feeder.list_s3_keys(bucket="bucket", prefix="nothing/here")


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


def _feed_result(
    name: str, ok: int = 10, errors: list | None = None
) -> feeder.FeedResult:
    return feeder.FeedResult(
        feed_paths=[Path(name)],
        input_count=ok,
        operation_count=ok,
        ok_count=ok,
        feeder_error_count=0,
        throttled_count=0,
        other_http_error_count=0,
        errors=errors or [],
    )


class _FakeFuture:
    """What `feed_batch.submit` hands back, wrapping one batch's outcome."""

    def __init__(self, outcome: feeder.FeedResult | BaseException) -> None:
        self.outcome = outcome

    def result(self, timeout=None, raise_on_failure=True):
        if raise_on_failure and isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _ExplodingFuture:
    """A future that fails the drain loop itself, the way a mid-run cancel does."""

    def result(self, timeout=None, raise_on_failure=True):
        raise KeyboardInterrupt("cancelled mid-drain")


class _FakeFeedBatch:
    def __init__(self, futures) -> None:
        self.futures = list(futures)
        self.submitted = 0
        self.calls: list[dict] = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        future = self.futures[self.submitted]
        self.submitted += 1
        return future


@pytest.fixture
def summary_artifacts(monkeypatch):
    """Stubs everything `vespa_feeder` touches bar the batches, capturing artifacts."""
    artifacts = []
    monkeypatch.setenv("VESPA_CLI_DATA_PLANE_TOKEN", "")
    monkeypatch.setattr(feeder, "get_ssm_parameter", lambda name: "stub")  # noqa: ARG005
    monkeypatch.setattr(feeder, "get_run_logger", lambda: logging.getLogger("test"))
    monkeypatch.setattr(
        feeder, "_terminate_vespa_feed_processes_on_sigterm_handler", lambda: None
    )
    monkeypatch.setattr(
        feeder, "create_markdown_artifact", lambda **kwargs: artifacts.append(kwargs)
    )
    return artifacts


def test_vespa_feeder_keeps_the_good_batches_when_one_raises(
    monkeypatch, summary_artifacts
):
    """
    A batch that raises must not take the rest of the run down with it.

    Keys under a `latest/` prefix get rewritten mid-run, so a lone 404 is
    routine. Collecting with `raise_on_failure=True` used to abandon the
    batches still in flight and skip the summary artifact entirely.
    """
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b", "c"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch(
            [
                _FakeFuture(_feed_result("one.jsonl")),
                _FakeFuture(RuntimeError("HeadObject: Not Found")),
                _FakeFuture(_feed_result("three.jsonl")),
            ]
        ),
    )

    with pytest.raises(feeder.VespaFeederFailed) as exc_info:
        feeder.vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    assert [str(crash) for crash in exc_info.value.crashes] == ["HeadObject: Not Found"]
    assert exc_info.value.failed_results == []

    markdown = summary_artifacts[0]["markdown"]
    assert "| Files processed | 2 |" in markdown
    assert "| Batches that raised | 1 |" in markdown
    assert "| `RuntimeError` | HeadObject: Not Found |" in markdown


def test_vespa_feeder_writes_the_summary_when_the_drain_is_cancelled(
    monkeypatch, summary_artifacts
):
    """
    A cancel lands in the drain loop, not in a batch.

    `raise_on_failure=False` keeps batch failures out of the control flow, so
    the `finally` exists for this: a run stopped part-way still reports what
    it fed.
    """
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch([_FakeFuture(_feed_result("one.jsonl")), _ExplodingFuture()]),
    )

    with pytest.raises(KeyboardInterrupt):
        feeder.vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    assert "| Files processed | 1 |" in summary_artifacts[0]["markdown"]


def test_vespa_feeder_writes_the_summary_and_returns_when_every_batch_works(
    monkeypatch, summary_artifacts
):
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch(
            [
                _FakeFuture(_feed_result("one.jsonl")),
                _FakeFuture(_feed_result("two.jsonl")),
            ]
        ),
    )

    feeder.vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    markdown = summary_artifacts[0]["markdown"]
    assert "✅ **All files indexed successfully**" in markdown
    assert "| Batches that raised | 0 |" in markdown


@pytest.mark.parametrize(
    ("s3_prefix", "s3_export_prefix", "expected_resolved", "expected_fed"),
    [
        pytest.param(
            "an/export/prefix/",
            None,
            True,
            "an/export/prefix/20260929T010000Z/part.jsonl",
            id="export-resolved",
        ),
        pytest.param(
            "an/export/prefix/",
            "20260922T190625Z",
            False,
            "an/export/prefix/20260922T190625Z/part.jsonl",
            id="export-pinned",
        ),
        # @related: LABEL_RELATIONSHIPS_DO_NOT_EXIST - labels feeds one fixed
        # JSONL from cpr-cache: the prefix is already the whole key, so there
        # is no export to resolve and nothing to list.
        pytest.param(
            "search/vespa/labels_feed_materializer.jsonl",
            None,
            False,
            "search/vespa/labels_feed_materializer.jsonl",
            id="single-jsonl",
        ),
    ],
)
def test_vespa_feeder_resolves_the_export_prefix_only_when_there_is_one(
    monkeypatch,
    summary_artifacts,
    s3_prefix,
    s3_export_prefix,
    expected_resolved,
    expected_fed,
):
    resolved = []

    def _resolve(bucket: str, prefix: str) -> str:  # noqa: ARG001
        resolved.append(prefix)
        return "20260929T010000Z"

    monkeypatch.setattr(feeder, "get_latest_s3_export_prefix", _resolve)
    monkeypatch.setattr(
        feeder,
        "list_s3_keys",
        lambda bucket, prefix: [f"{prefix}/part.jsonl"],  # noqa: ARG005
    )
    feed_batch = _FakeFeedBatch([_FakeFuture(_feed_result("one.jsonl"))])
    monkeypatch.setattr(feeder, "feed_batch", feed_batch)

    feeder.vespa_feeder(
        s3_bucket="bucket",
        s3_prefix=s3_prefix,
        s3_export_prefix=s3_export_prefix,
        batch_size=1,
    )

    assert bool(resolved) is expected_resolved
    assert [call["batched_s3_keys"] for call in feed_batch.calls] == [(expected_fed,)]
