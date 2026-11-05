"""Table-driven tests for the `vespa_feeder` flow itself."""

import inspect
import logging
import subprocess
from pathlib import Path

import pytest
import vespa_feeder as feeder
from helpers import FakeVespaFeedProcess
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util._once import Once
from prefect.futures import PrefectFuture
from prefect.logging import disable_run_logger


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


# Captured at import, before any test monkeypatches `feeder.feed_batch` with a
# fake: `.fn` is the real function the Prefect task wraps.
_REAL_FEED_BATCH_PARAMETERS = set(inspect.signature(feeder.feed_batch.fn).parameters)


class _FakeFuture:
    """
    What `feed_batch.submit` hands back, wrapping one batch's outcome.

    `raise_on_failure=False` is what the drain loop passes, and a real future
    honours it by returning the exception rather than raising it. Set
    `ignores_raise_on_failure` for the other case: an interruption that fails
    the drain loop itself -- a cancel, or a flow-level timeout -- which arrives
    regardless of what the caller asked for.
    """

    def __init__(
        self,
        outcome: feeder.FeedResult | BaseException,
        ignores_raise_on_failure: bool = False,
    ) -> None:
        self.outcome = outcome
        self.ignores_raise_on_failure = ignores_raise_on_failure

    def result(self, timeout=None, raise_on_failure=True):
        if isinstance(self.outcome, BaseException) and (
            raise_on_failure or self.ignores_raise_on_failure
        ):
            raise self.outcome
        return self.outcome


def _contract(func):
    # Names and defaults, not annotations: the fakes are deliberately
    # unannotated, but the parameters the production code passes must match.
    return [
        (name, parameter.kind, parameter.default)
        for name, parameter in inspect.signature(func).parameters.items()
    ]


def test_the_future_fake_matches_the_real_prefect_future():
    """
    The fake must keep the `.result` signature it stands in for.

    `vespa_feeder` calls `.result(raise_on_failure=False)`; if Prefect renamed
    that parameter the fake would happily keep accepting it and the drain-loop
    tests would still pass against an API that no longer exists.
    """
    assert _contract(_FakeFuture.result) == _contract(PrefectFuture.result)


@pytest.mark.parametrize(
    "method", ["communicate", "terminate", "kill", "__enter__", "__exit__"]
)
def test_the_vespa_feed_process_fake_matches_the_real_popen(method):
    """
    The `Popen` stand-in must keep the signatures it stands in for.

    `feed_derived_files` drives a real `subprocess.Popen` in production. If the
    stdlib changed one of these signatures -- or the fake drifted from it --
    every feed test would still pass against an API that no longer matches.
    """
    assert _contract(getattr(FakeVespaFeedProcess, method)) == _contract(
        getattr(subprocess.Popen, method)
    )


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
    monkeypatch.setattr(
        feeder, "_terminate_vespa_feed_processes_on_sigterm_handler", lambda: None
    )
    monkeypatch.setattr(
        feeder, "create_markdown_artifact", lambda **kwargs: artifacts.append(kwargs)
    )
    # Prefect's own stand-in for a run context, so `get_run_logger()` inside
    # `vespa_feeder` returns a plain logger instead of raising
    # MissingContextError - no patching of the production module needed.
    with disable_run_logger():
        yield artifacts


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
        _FakeFeedBatch(
            [
                _FakeFuture(_feed_result("one.jsonl")),
                _FakeFuture(
                    KeyboardInterrupt("cancelled mid-drain"),
                    ignores_raise_on_failure=True,
                ),
            ]
        ),
    )

    with pytest.raises(KeyboardInterrupt):
        feeder.vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    assert "| Files processed | 1 |" in summary_artifacts[0]["markdown"]


def test_vespa_feeder_records_a_cancelled_run_as_neither_outcome(
    monkeypatch, summary_artifacts, recording_metrics, prefect_run_identity
):
    """
    A cancel mid-drain is neither a completed run nor a failed one.

    Counting it completed is the failure mode hardest to notice: a run
    stopped after 1 of 2 batches would read as a clean success, while
    runs.completed and runs.failed are the natural numerator and
    denominator for a success-rate panel. Counting it failed would page
    someone for an operator's own decision. The duration is still recorded,
    because the run did consume that time.
    """
    expected_deployment, expected_run_name = prefect_run_identity
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch(
            [
                _FakeFuture(_feed_result("one.jsonl")),
                _FakeFuture(
                    KeyboardInterrupt("cancelled mid-drain"),
                    ignores_raise_on_failure=True,
                ),
            ]
        ),
    )

    with pytest.raises(KeyboardInterrupt):
        feeder.vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    recording_metrics.record_run_completed.assert_not_called()
    recording_metrics.record_run_failed.assert_not_called()

    recording_metrics.record_run_duration.assert_called_once()
    duration_s, deployment_name, run_name = (
        recording_metrics.record_run_duration.call_args.args
    )
    assert duration_s >= 0
    assert deployment_name == expected_deployment
    assert run_name == expected_run_name


def test_vespa_feeder_terminates_in_flight_feeds_when_the_drain_is_interrupted(
    monkeypatch, summary_artifacts
):
    """
    An interrupted run must not leave orphaned `vespa feed` children running.

    A flow-level timeout raises on the main thread via Prefect's
    AlarmCancelScope, but worker threads blocked in `communicate()` never see
    it. Without this the run fails while orphaned children keep writing to
    Vespa until the container dies.

    Prefect owns SIGALRM, so we hook the drain `finally` rather than
    installing a competing signal handler.
    """
    process = FakeVespaFeedProcess(None, ["vespa", "feed"], "")
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch(
            [
                _FakeFuture(
                    KeyboardInterrupt("cancelled mid-drain"),
                    ignores_raise_on_failure=True,
                )
            ]
        ),
    )

    with feeder._vespa_feed_processes_lock:
        feeder._vespa_feed_processes.add(process)
    try:
        with pytest.raises(KeyboardInterrupt):
            feeder.vespa_feeder(
                s3_bucket="bucket",
                s3_prefix="prefix/",
                s3_export_prefix="x",
                batch_size=1,
            )
    finally:
        with feeder._vespa_feed_processes_lock:
            feeder._vespa_feed_processes.discard(process)

    assert process.terminated


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


def test_vespa_feeder_records_a_completed_run(
    monkeypatch, summary_artifacts, recording_metrics, prefect_run_identity
):
    expected_deployment, expected_run_name = prefect_run_identity
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

    # record_run_duration is called positionally, so read the args the same way.
    # run_name rides along so a duration can be attributed to a specific run,
    # which is what answers "is the feeder getting slower?".
    recording_metrics.record_run_duration.assert_called_once()
    duration_s, deployment_name, run_name = (
        recording_metrics.record_run_duration.call_args.args
    )
    assert duration_s >= 0
    assert deployment_name == expected_deployment
    assert run_name == expected_run_name

    recording_metrics.record_run_completed.assert_called_once_with(
        expected_deployment, expected_run_name
    )
    recording_metrics.record_run_failed.assert_not_called()


def test_vespa_feeder_records_a_failed_run(
    monkeypatch, summary_artifacts, recording_metrics, prefect_run_identity
):
    """A run that loses records is a failed run, not a completed one."""
    expected_deployment, expected_run_name = prefect_run_identity
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch(
            [
                _FakeFuture(
                    _feed_result(
                        "one.jsonl",
                        errors=[
                            feeder.VespaResponseError(
                                ok_count=8,
                                operation_count=10,
                                throttled_count=0,
                                other_http_error_count=0,
                                failed_documents=[],
                            )
                        ],
                    )
                )
            ]
        ),
    )

    with pytest.raises(feeder.VespaFeederFailed):
        feeder.vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    recording_metrics.record_run_failed.assert_called_once_with(
        expected_deployment, expected_run_name
    )
    recording_metrics.record_run_completed.assert_not_called()
    recording_metrics.record_run_duration.assert_called_once()


def test_vespa_feeder_sets_the_feed_stats_the_slack_hook_reads(
    monkeypatch, summary_artifacts, recording_metrics
):
    """
    Slack prints `—` unless `set_feed_stats` runs.

    The totals must be the run's, not the last batch's, and must match the
    numbers in the summary artifact.
    """
    captured: list[dict] = []
    monkeypatch.setattr(
        feeder,
        "set_feed_stats",
        lambda input_count, ok_count, total_errors: captured.append(
            {
                "input": input_count,
                "ok": ok_count,
                "errors": total_errors,
            }
        ),
    )
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch(
            [
                _FakeFuture(_feed_result("one.jsonl", ok=10)),
                _FakeFuture(_feed_result("two.jsonl", ok=5)),
            ]
        ),
    )

    feeder.vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    assert captured == [{"input": 15, "ok": 15, "errors": 0}]

    # The comment in vespa_feeder says these cannot disagree - prove it.
    markdown = summary_artifacts[0]["markdown"]
    assert f"| Input records | {captured[0]['input']} |" in markdown
    assert f"| OK | {captured[0]['ok']} |" in markdown


@pytest.fixture
def telemetry_calls(monkeypatch):
    """Records the order force_flush and shutdown are called in."""
    calls: list[str] = []
    monkeypatch.setattr(feeder, "force_flush", lambda: calls.append("force_flush"))
    monkeypatch.setattr(feeder, "shutdown", lambda: calls.append("shutdown"))
    return calls


def test_vespa_feeder_flushes_then_shuts_down_telemetry(
    monkeypatch, summary_artifacts, recording_metrics, telemetry_calls
):
    """
    Order matters.

    force_flush exports metrics and logs with a bounded timeout and a logged
    warning, then shutdown exports the spans nothing else flushes.
    """
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder, "feed_batch", _FakeFeedBatch([_FakeFuture(_feed_result("one.jsonl"))])
    )

    feeder.vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    assert telemetry_calls == ["force_flush", "shutdown"]


def test_vespa_feeder_closes_the_run_span_before_shutting_telemetry_down(
    monkeypatch, summary_artifacts, recording_metrics
):
    """
    shutdown() tears the tracer provider down.

    Any span still open when it runs is dropped by the BatchSpanProcessor, so
    the root vespa_feeder span has to end first. The decorator form held it
    open across the whole finally, losing the root span on every run; only an
    explicit `with` closes it before the flush.
    """
    # Under test the module tracer is a no-op ProxyTracer, whose spans never
    # record - so it cannot tell an open span from a closed one. A ProxyTracer
    # resolves the global provider when the span is started, so installing a
    # real one makes the run span record whether it came from a decorator or a
    # `with`.
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", TracerProvider())
    monkeypatch.setattr(trace, "_TRACER_PROVIDER_SET_ONCE", Once())

    # Sampled at the moment shutdown runs, not afterwards: the span ends either
    # way once vespa_feeder returns, so a span object kept for later always
    # looks closed.
    recording_at_shutdown: list[bool] = []

    def _record_span_state() -> None:
        recording_at_shutdown.append(trace.get_current_span().is_recording())

    monkeypatch.setattr(feeder, "force_flush", lambda: None)
    monkeypatch.setattr(feeder, "shutdown", _record_span_state)

    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder, "feed_batch", _FakeFeedBatch([_FakeFuture(_feed_result("one.jsonl"))])
    )

    feeder.vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    # No span is still recording when shutdown runs, so the run span has
    # already ended and cannot be dropped.
    assert recording_at_shutdown == [False]


def test_vespa_feeder_flushes_telemetry_when_the_run_fails(
    monkeypatch, summary_artifacts, recording_metrics, telemetry_calls
):
    """A failed run is exactly when the metrics matter most."""
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _FakeFeedBatch([_FakeFuture(RuntimeError("HeadObject: Not Found"))]),
    )

    with pytest.raises(feeder.VespaFeederFailed):
        feeder.vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    assert telemetry_calls == ["force_flush", "shutdown"]


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

    # The fake stands in for a Prefect `Task`, so every keyword the drain loop
    # passes has to be a real parameter of the task's own function. Matching
    # `Task.submit` itself would be noise - it takes `*args`, `return_state`
    # and `wait_for` that the loop never passes - but a rename on `feed_batch`
    # would otherwise leave the fake accepting an argument that no longer
    # exists, with every drain-loop test still green.
    for call in feed_batch.calls:
        assert set(call) <= _REAL_FEED_BATCH_PARAMETERS


class _RecordingLogger:
    """Captures the lines `vespa_feeder` writes via `get_run_logger()`."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    def info(self, message: str) -> None:
        self.messages.append(message)

    def error(self, message: str) -> None:
        self.messages.append(message)


def test_vespa_feeder_does_not_log_per_batch_progress_while_only_enqueueing(
    monkeypatch, summary_artifacts
):
    """
    The submit loop must not claim per-batch progress it has not made.

    `feed_batch.submit()` only enqueues, so the loop runs to completion in
    seconds. A "Feeding batch N/M" line here reads as progress while
    reporting none: run 06aea240 printed all 589 of them in 3 seconds, then
    fed 32 batches before wedging, and the log tail read like a finished run.
    """
    # `disable_run_logger()` (via summary_artifacts) routes `get_run_logger()`
    # to a disabled logger caplog cannot see, so capture the lines directly.
    logged: list[str] = []
    monkeypatch.setattr(feeder, "get_run_logger", lambda: _RecordingLogger(logged))
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder, "feed_batch", _FakeFeedBatch([_FakeFuture(_feed_result("one.jsonl"))])
    )

    feeder.vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=2
    )

    assert not [message for message in logged if message.startswith("Feeding batch ")]
    assert "Queued 1 batch(es) onto the task runner; 2 file(s) total" in logged
