"""Table-driven tests for the `feed_batch` task and the metrics it records."""

import subprocess

import pytest
import vespa_feeder as feeder
from helpers import _FakeVespaFeed, put_s3_objects, vespa_feed_stdout


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
    s3_client,
    s3_bucket,
    s3_objects,
    batched_s3_keys,
    derive_data_from_source,
    expected_records,
):
    put_s3_objects(s3_client, s3_bucket, s3_objects)
    fake_feed = _FakeVespaFeed()
    monkeypatch.setattr(feeder.subprocess, "Popen", fake_feed)

    result = feeder.feed_batch.fn(
        endpoint="http://vespa",
        application="app",
        connections=2,
        feed_timeout_seconds_per_file=300,
        s3_bucket=s3_bucket,
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


def _broken_deriver(record: dict) -> dict:
    raise RuntimeError("deriver failed")


@pytest.mark.parametrize(
    ("break_the_last_download", "derive_data_from_source", "vespa_feed", "expected_exception"),
    [
        pytest.param(
            True,
            None,
            _FakeVespaFeed,
            RuntimeError,
            id="a-download-fails",
        ),
        pytest.param(
            False,
            _broken_deriver,
            _FakeVespaFeed,
            RuntimeError,
            id="the-deriver-raises",
        ),
        pytest.param(
            False,
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
    s3_bucket,
    break_the_last_download,
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
    put_s3_objects(s3_client, s3_bucket, _BATCH_S3_OBJECTS)
    if break_the_last_download:
        # moto serves real objects but has no fault injection, so the last
        # download is failed by hand. The earlier ones still run for real,
        # which is what leaves the batch partway through on disk.
        last_key = list(_BATCH_S3_OBJECTS)[-1]
        real_download_file = s3_client.download_file

        def download_file(bucket: str, key: str, destination: str) -> None:
            if key == last_key:
                raise RuntimeError("s3 download failed")
            real_download_file(bucket, key, destination)

        monkeypatch.setattr(s3_client, "download_file", download_file)
        monkeypatch.setattr(feeder.boto3, "client", lambda _: s3_client)
    monkeypatch.setattr(feeder.subprocess, "Popen", vespa_feed())

    with pytest.raises(expected_exception):
        feeder.feed_batch.fn(
            endpoint="http://vespa",
            application="app",
            connections=2,
            feed_timeout_seconds_per_file=300,
            s3_bucket=s3_bucket,
            batched_s3_keys=tuple(_BATCH_S3_OBJECTS),
            derive_data_from_source=derive_data_from_source,
        )

    assert list(temp_workspace.iterdir()) == []


def test_feed_batch_records_what_it_fed(
    monkeypatch, temp_workspace, s3_client, s3_bucket, recording_metrics
):
    """
    `records.error` is operation - ok, the only count that means records were lost.

    feeder/throttled/other-HTTP errors are retry attempts that mostly
    self-heal, so they must not inflate the error metric.
    """
    put_s3_objects(s3_client, s3_bucket, _BATCH_S3_OBJECTS)
    monkeypatch.setattr(feeder.subprocess, "Popen", _FakeVespaFeed())

    feeder.feed_batch.fn(
        endpoint="http://vespa",
        application="app",
        connections=2,
        feed_timeout_seconds_per_file=300,
        s3_bucket=s3_bucket,
        batched_s3_keys=tuple(_BATCH_S3_OBJECTS),
    )

    recording_metrics.record_feed_stats.assert_called_once_with(
        input_count=2,
        ok_count=2,
        total_errors=0,
        deployment_name="local",
        run_name="unknown",
    )

    # The duration is whatever the clock said, so only its shape is assertable.
    recording_metrics.record_task_duration.assert_called_once()
    task_duration = recording_metrics.record_task_duration.call_args.kwargs
    assert task_duration["task_name"] == "feed_batch"
    assert task_duration["duration_s"] >= 0


def test_feed_batch_records_its_duration_even_when_it_fails(
    monkeypatch, temp_workspace, s3_client, s3_bucket, recording_metrics
):
    """A batch that raises still took time; the timing must not be lost with it."""
    put_s3_objects(s3_client, s3_bucket, _BATCH_S3_OBJECTS)

    # moto serves real objects but has no fault injection, so the download is
    # failed by hand - the same inline pattern
    # `test_feed_batch_leaves_nothing_on_disk_when_it_fails` uses.
    def download_file(bucket: str, key: str, destination: str) -> None:
        raise RuntimeError("s3 download failed")

    monkeypatch.setattr(s3_client, "download_file", download_file)
    monkeypatch.setattr(feeder.boto3, "client", lambda _: s3_client)  # noqa: ARG005
    monkeypatch.setattr(feeder.subprocess, "Popen", _FakeVespaFeed())

    with pytest.raises(RuntimeError, match="s3 download failed"):
        feeder.feed_batch.fn(
            endpoint="http://vespa",
            application="app",
            connections=2,
            feed_timeout_seconds_per_file=300,
            s3_bucket=s3_bucket,
            batched_s3_keys=tuple(_BATCH_S3_OBJECTS),
        )

    recording_metrics.record_feed_stats.assert_not_called()
    recording_metrics.record_task_duration.assert_called_once()
    assert (
        recording_metrics.record_task_duration.call_args.kwargs["task_name"]
        == "feed_batch"
    )


@pytest.mark.parametrize(
    ("stdout", "expected_errors"),
    [
        pytest.param(
            vespa_feed_stdout(operation=2, ok=2, feeder_error_count=3),
            0,
            id="retries-that-self-healed-do-not-count-as-lost",
        ),
        pytest.param(
            vespa_feed_stdout(operation=2, ok=1),
            1,
            id="a-record-that-never-landed-counts-as-lost",
        ),
    ],
)
def test_feed_batch_counts_only_records_that_were_actually_lost(
    monkeypatch,
    temp_workspace,
    s3_client,
    s3_bucket,
    recording_metrics,
    stdout,
    expected_errors,
):
    """
    `records.error` must track lost records, not retry attempts.

    `feeder_error_count` counts transport-layer retries, which mostly
    self-heal - counting those would report data loss that never happened.
    """
    put_s3_objects(s3_client, s3_bucket, _BATCH_S3_OBJECTS)
    monkeypatch.setattr(feeder.subprocess, "Popen", _FakeVespaFeed(stdout))

    feeder.feed_batch.fn(
        endpoint="http://vespa",
        application="app",
        connections=2,
        feed_timeout_seconds_per_file=300,
        s3_bucket=s3_bucket,
        batched_s3_keys=tuple(_BATCH_S3_OBJECTS),
    )

    assert (
        recording_metrics.record_feed_stats.call_args.kwargs["total_errors"]
        == expected_errors
    )
