"""Table-driven tests for the `vespa_feeder` flow itself."""

import inspect
from pathlib import Path

import pytest
import vespa_feeder as feeder
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


@pytest.mark.parametrize("fake", [_FakeFuture, _ExplodingFuture])
def test_the_future_fakes_match_the_real_prefect_future(fake):
    """
    The fakes must keep the `.result` signature they stand in for.

    `vespa_feeder` calls `.result(raise_on_failure=False)`; if Prefect renamed
    that parameter the fakes would happily keep accepting it and the drain-loop
    tests would still pass against an API that no longer exists.
    """

    def _contract(func):
        # Names and defaults, not annotations: the fakes are deliberately
        # unannotated, but the parameters the drain loop passes must match.
        return [
            (name, parameter.kind, parameter.default)
            for name, parameter in inspect.signature(func).parameters.items()
        ]

    assert _contract(fake.result) == _contract(PrefectFuture.result)


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

def test_vespa_feeder_records_a_completed_run(
    monkeypatch, summary_artifacts, recording_metrics
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

    # record_run_duration is called positionally, so read the args the same way.
    recording_metrics.record_run_duration.assert_called_once()
    duration_s, deployment_name = recording_metrics.record_run_duration.call_args.args
    assert duration_s >= 0
    assert deployment_name == "local"

    recording_metrics.record_run_completed.assert_called_once_with("local", "unknown")
    recording_metrics.record_run_failed.assert_not_called()


def test_vespa_feeder_records_a_failed_run(
    monkeypatch, summary_artifacts, recording_metrics
):
    """A run that loses records is a failed run, not a completed one."""
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

    recording_metrics.record_run_failed.assert_called_once_with("local", "unknown")
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
