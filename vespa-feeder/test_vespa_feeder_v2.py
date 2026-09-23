"""Step-by-step tests for the v2 feeder, plus one end-to-end run of the flow."""

import json
import subprocess
import tempfile
from itertools import takewhile
from pathlib import Path

import cloudpickle
import orjson
import pytest
import vespa_feeder_v2 as feeder
from prefect.settings import PREFECT_TASKS_REFRESH_CACHE, temporary_settings

from prefect import flow


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


class _FakeVespaFeed:
    """
    Stands in for `subprocess.run`, recording what `vespa feed` was handed.

    It reads the feed files off disk at call time, so `fed_records` is proof the
    files still existed and held records at the moment they were fed.
    """

    def __init__(self, stdout: str | None = None, stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[list[str]] = []
        self.timeouts: list[int] = []
        self.fed_records: list[dict] = []

    def __call__(self, argv: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        self.timeouts.append(kwargs["timeout"])

        feed_paths = takewhile(lambda arg: not arg.startswith("--"), argv[2:])
        records = [record for path in feed_paths for record in _read_jsonl(Path(path))]
        self.fed_records.extend(records)

        stdout = self.stdout or _vespa_feed_stdout(
            operation=len(records), ok=len(records)
        )
        return subprocess.CompletedProcess(argv, 0, stdout, self.stderr)


@pytest.fixture
def temp_workspace(monkeypatch, tmp_path: Path) -> Path:
    """Point the feeder's `tempfile.gettempdir()` at a per-test directory."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path


def test_materialize_s3_files_writes_one_file_per_key(monkeypatch, temp_workspace):
    monkeypatch.setattr(
        feeder.boto3,
        "client",
        lambda _: _FakeS3({"prefix/one.jsonl": b'{"id": 1}\n'}),
    )

    paths = feeder.materialize_s3_files(
        bucket="bucket", batched_s3_keys=["prefix/one.jsonl"]
    )

    assert paths == [temp_workspace / "one.jsonl"]
    assert _read_jsonl(paths[0]) == [{"id": 1}]


def test_materialize_derived_files_applies_the_deriver(tmp_path):
    source = _write_jsonl(tmp_path / "one.jsonl", [{"id": 1}, {"id": 2}])

    derived = feeder.materialize_derived_files(
        materialized_s3_files=[source],
        derive_data_from_source=lambda record: record | {"derived": True},
    )

    assert derived == [tmp_path / "one.derived.jsonl"]
    assert _read_jsonl(derived[0]) == [
        {"id": 1, "derived": True},
        {"id": 2, "derived": True},
    ]


def test_materialize_derived_files_writes_new_files_without_a_deriver(tmp_path):
    """
    The no-deriver path must not hand the sources back.

    `feed_batch` deletes the sources the moment this returns, so aliasing the
    two lists would delete the files about to be fed.
    """
    source = _write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])

    derived = feeder.materialize_derived_files(
        materialized_s3_files=[source], derive_data_from_source=None
    )

    assert derived == [tmp_path / "one.derived.jsonl"]
    assert source.exists()
    assert _read_jsonl(derived[0]) == [{"id": 1}]


def test_materialize_derived_files_skips_blank_lines(tmp_path):
    source = tmp_path / "one.jsonl"
    source.write_bytes(b'{"id": 1}\n\n\n{"id": 2}\n')

    derived = feeder.materialize_derived_files(
        materialized_s3_files=[source], derive_data_from_source=None
    )

    assert _read_jsonl(derived[0]) == [{"id": 1}, {"id": 2}]


def test_feed_derived_files_feeds_every_file_in_one_subprocess(monkeypatch, tmp_path):
    files = [
        _write_jsonl(tmp_path / f"{n}.jsonl", [{"id": n}, {"id": n + 100}])
        for n in range(3)
    ]
    fake_feed = _FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "run", fake_feed)

    result = feeder.feed_derived_files(
        materialized_derived_files=files,
        endpoint="http://vespa",
        application="app",
        feed_timeout_seconds_per_file=300,
    )

    assert len(fake_feed.calls) == 1
    assert fake_feed.calls[0][:2] == ["vespa", "feed"]
    assert fake_feed.calls[0][2:5] == [str(path) for path in files]
    assert fake_feed.timeouts == [900]
    assert result.input_count == 6
    assert result.operation_count == 6
    assert result.ok_count == 6
    assert result.errors == []


def test_feed_derived_files_does_not_fail_a_file_whose_retries_succeeded(
    monkeypatch, tmp_path
):
    """Throttling that eventually succeeded is not a lost record."""
    files = [_write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    monkeypatch.setattr(
        feeder.subprocess,
        "run",
        _FakeVespaFeed(
            _vespa_feed_stdout(operation=10, ok=10, code_counts={"200": 10, "429": 4})
        ),
    )

    result = feeder.feed_derived_files(
        materialized_derived_files=files, endpoint="http://vespa", application="app"
    )

    assert result.throttled_count == 4
    assert result.errors == []


def test_feed_derived_files_reports_missing_records_and_splits_429s(
    monkeypatch, tmp_path
):
    files = [_write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]
    monkeypatch.setattr(
        feeder.subprocess,
        "run",
        _FakeVespaFeed(
            _vespa_feed_stdout(
                operation=10, ok=8, code_counts={"200": 8, "429": 5, "503": 2}
            ),
            stderr="feed: 503 Service Unavailable for put id:doc:doc::9: giving up\n",
        ),
    )

    result = feeder.feed_derived_files(
        materialized_derived_files=files, endpoint="http://vespa", application="app"
    )

    assert result.throttled_count == 5
    assert result.other_http_error_count == 2
    assert [type(error) for error in result.errors] == [feeder.VespaResponseError]
    assert result.errors[0].failed_documents == [
        feeder.FailedDocument(doc_id="id:doc:doc::9", error="503 Service Unavailable")
    ]


def test_feed_derived_files_raises_when_the_cli_exits_non_zero(monkeypatch, tmp_path):
    files = [_write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])]

    with pytest.raises(subprocess.CalledProcessError):
        feeder.feed_derived_files(
            materialized_derived_files=files,
            endpoint="http://127.0.0.1:1",
            application="app",
        )


def test_delete_materialized_files_tolerates_an_already_missing_file(tmp_path):
    present = _write_jsonl(tmp_path / "one.jsonl", [{"id": 1}])
    absent = tmp_path / "gone.jsonl"

    feeder.delete_materialized_s3_files([present, absent])
    feeder.delete_materialized_derived_files([present, absent])

    assert not present.exists()


@pytest.mark.parametrize(
    "derive_data_from_source",
    [
        pytest.param(None, id="no-deriver"),
        pytest.param(lambda record: record | {"derived": True}, id="with-deriver"),
    ],
)
def test_feed_batch_feeds_the_records_then_leaves_nothing_on_disk(
    monkeypatch, temp_workspace, derive_data_from_source
):
    monkeypatch.setattr(
        feeder.boto3,
        "client",
        lambda _: _FakeS3({"prefix/one.jsonl": b'{"id": 1}\n{"id": 2}\n'}),
    )
    fake_feed = _FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "run", fake_feed)

    result = feeder.feed_batch.fn(
        endpoint="http://vespa",
        application="app",
        connections=2,
        feed_timeout_seconds_per_file=300,
        s3_bucket="bucket",
        batched_s3_keys=("prefix/one.jsonl",),
        derive_data_from_source=derive_data_from_source,
    )

    assert [record["id"] for record in fake_feed.fed_records] == [1, 2]
    assert result.ok_count == 2
    assert result.errors == []
    assert list(temp_workspace.iterdir()) == []


@flow
def _feeder_flow(**kwargs):
    return feeder.vespa_feeder_v2(**kwargs)


@pytest.fixture
def feeder_flow_env(monkeypatch, temp_workspace):
    """Stub S3, SSM and the `vespa feed` CLI out from under the whole flow."""
    s3_keys = [f"prefix/{n}.jsonl" for n in range(5)]
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, key: s3_keys)
    monkeypatch.setattr(feeder, "get_ssm_parameter", lambda name: "stub")
    monkeypatch.setattr(
        feeder.boto3,
        "client",
        lambda _: _FakeS3({key: b'{"id": 1}\n' for key in s3_keys}),
    )
    # The flow writes this itself; set it here so monkeypatch restores it.
    monkeypatch.setenv("VESPA_CLI_DATA_PLANE_TOKEN", "")

    # feed_batch's cache key is its inputs, which are identical across these
    # tests - without this the second run is served from the first one's cache
    # and never feeds anything.
    with temporary_settings({PREFECT_TASKS_REFRESH_CACHE: True}):
        yield _FakeVespaFeed()


def test_vespa_feeder_v2_feeds_every_batch(
    monkeypatch, prefect_db, temp_workspace, feeder_flow_env
):
    monkeypatch.setattr(feeder.subprocess, "run", feeder_flow_env)

    assert _feeder_flow(s3_bucket="bucket", s3_key="prefix", batch_size=2) is None
    # 5 keys at batch_size=2 is three `vespa feed` invocations, one per batch.
    assert len(feeder_flow_env.calls) == 3
    assert len(feeder_flow_env.fed_records) == 5
    assert list(temp_workspace.iterdir()) == []


def test_vespa_feeder_v2_raises_with_every_failed_batch_when_records_are_missing(
    monkeypatch, prefect_db, temp_workspace, feeder_flow_env
):
    feeder_flow_env.stdout = _vespa_feed_stdout(operation=2, ok=1)
    monkeypatch.setattr(feeder.subprocess, "run", feeder_flow_env)

    with pytest.raises(feeder.VespaFeederFailed) as raised:
        _feeder_flow(s3_bucket="bucket", s3_key="prefix", batch_size=2)

    assert "failed for 3/3 batch(es)" in str(raised.value)
    assert len(raised.value.failed_results) == 3
    # Every batch is still fed before the run fails, so the summary is complete.
    assert len(feeder_flow_env.calls) == 3


def test_vespa_feed_failed_survives_the_pickling_prefect_does_to_persist_it(tmp_path):
    """
    `@dataclass` on an Exception leaves `args` empty under keyword construction

    which makes `str()` empty and unpickling raise. This must not regress.
    """
    result = feeder.FeedResult(
        feed_paths=[tmp_path / "one.jsonl"],
        input_count=2,
        operation_count=2,
        ok_count=1,
        feeder_error_count=0,
        throttled_count=0,
        other_http_error_count=0,
        errors=[feeder.VespaResponseError(1, 2, 0, 0, [])],
    )
    error = feeder.VespaFeederFailed("1/1 batch(es) failed", [result])

    revived = cloudpickle.loads(cloudpickle.dumps(error))

    assert str(revived) == "1/1 batch(es) failed"
    assert revived.failed_results == [result]


def test_vespa_feeder_v2_rejects_an_out_of_range_sample_rate(
    monkeypatch, prefect_db, temp_workspace, feeder_flow_env
):
    monkeypatch.setattr(feeder.subprocess, "run", feeder_flow_env)

    with pytest.raises(ValueError, match="sample_rate must be in"):
        _feeder_flow(s3_bucket="bucket", s3_key="prefix", sample_rate=0)

    assert feeder_flow_env.calls == []
