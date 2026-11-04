"""Table-driven tests for the `vespa_feeder` flow itself."""

from contextlib import contextmanager
from pathlib import Path

import pytest
import vespa_feeder as feeder
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util._once import Once
from prefect.cache_policies import NO_CACHE
from task_runner import task_runner

from prefect import flow, task


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


def _feed_batch_returning(*outcomes, record_calls_in: list | None = None):
    """
    A real Prefect task standing in for `feed_batch`, one outcome per batch.

    `vespa_feeder` calls `.submit()` on whatever `feed_batch` is, so this has
    to be a genuine task: it gives the flow real `PrefectFuture`s off the real
    `ThreadPoolTaskRunner`. Only the body is swapped - the real `feed_batch`
    shells out to the `vespa feed` binary, which is not available under test.

    Outcomes are handed out per call rather than per batch index because the
    task runner may run batches concurrently; a `BaseException` outcome is
    raised, so the engine marks that run failed exactly as a real failure does.

    `record_calls_in`, when given, collects the kwargs each batch was
    submitted with. It is a parameter rather than an attribute on the returned
    task because that task is a typed Prefect `Task`, which has no such field.
    """
    remaining = list(outcomes)

    @task(cache_policy=NO_CACHE)
    def fake_feed_batch(**kwargs) -> feeder.FeedResult:
        if record_calls_in is not None:
            record_calls_in.append(kwargs)
        outcome = remaining.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return fake_feed_batch


def _run_vespa_feeder(max_workers: int = 4, **kwargs) -> None:
    """
    Run `vespa_feeder` inside a real flow, the way the feeder flows do.

    `vespa_feeder` is a plain function, not a flow: it is called from the
    `@flow` wrappers in `labels_flow`/`documents_flow`/`passages_flow`. It
    submits tasks, so it needs a real flow run and task runner around it -
    the same bounded `task_runner` those flows pass.

    `max_workers=1` makes the batches run in submission order, for the tests
    that care which batch finishes first.
    """

    @flow(task_runner=task_runner(max_workers=max_workers))
    def feeder_flow() -> None:
        feeder.vespa_feeder(**kwargs)

    feeder_flow()


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
    # No `get_run_logger` stub: these tests run inside a real flow run, so the
    # real run context supplies the logger.
    return artifacts


def test_vespa_feeder_keeps_the_good_batches_when_one_raises(
    monkeypatch, prefect_db, summary_artifacts
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
        _feed_batch_returning(
            _feed_result("one.jsonl"),
            RuntimeError("HeadObject: Not Found"),
            _feed_result("three.jsonl"),
        ),
    )

    with pytest.raises(feeder.VespaFeederFailed) as exc_info:
        _run_vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    assert [str(crash) for crash in exc_info.value.crashes] == ["HeadObject: Not Found"]
    assert exc_info.value.failed_results == []

    markdown = summary_artifacts[0]["markdown"]
    assert "| Files processed | 2 |" in markdown
    assert "| Batches that raised | 1 |" in markdown
    assert "| `RuntimeError` | HeadObject: Not Found |" in markdown


def test_vespa_feeder_writes_the_summary_when_the_drain_is_cancelled(
    monkeypatch, prefect_db, summary_artifacts
):
    """
    A cancel lands in the drain loop, not in a batch.

    `raise_on_failure=False` keeps batch failures out of the control flow, so
    the `finally` exists for this: a run stopped part-way still reports what
    it fed.
    """
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    # The second batch raises KeyboardInterrupt, which `raise_on_failure=False`
    # does NOT swallow - BaseException propagates out of `.result()` and into
    # the drain loop, which is the code path under test. max_workers=1 so the
    # first batch is finished and collected before the second one interrupts.
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(
            _feed_result("one.jsonl"), KeyboardInterrupt("cancelled mid-drain")
        ),
    )

    with pytest.raises(KeyboardInterrupt):
        _run_vespa_feeder(
            s3_bucket="bucket",
            s3_prefix="prefix/",
            s3_export_prefix="x",
            batch_size=1,
            max_workers=1,
        )

    assert "| Files processed | 1 |" in summary_artifacts[0]["markdown"]


def test_vespa_feeder_writes_the_summary_and_returns_when_every_batch_works(
    monkeypatch, prefect_db, summary_artifacts
):
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(
            _feed_result("one.jsonl"),
            _feed_result("two.jsonl"),
        ),
    )

    _run_vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    markdown = summary_artifacts[0]["markdown"]
    assert "✅ **All files indexed successfully**" in markdown
    assert "| Batches that raised | 0 |" in markdown

def test_vespa_feeder_records_a_completed_run(
    monkeypatch, prefect_db, summary_artifacts, recording_metrics
):
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(
            _feed_result("one.jsonl"),
            _feed_result("two.jsonl"),
        ),
    )

    _run_vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    # record_run_duration is called positionally, so read the args the same way.
    recording_metrics.record_run_duration.assert_called_once()
    duration_s, deployment_name = recording_metrics.record_run_duration.call_args.args
    assert duration_s >= 0
    assert deployment_name == "local"

    # Under a real flow run the run name is Prefect's own generated one, not
    # the "unknown" fallback vespa_feeder uses outside a run context.
    recording_metrics.record_run_completed.assert_called_once()
    completed_deployment, completed_run_name = (
        recording_metrics.record_run_completed.call_args.args
    )
    assert completed_deployment == "local"
    assert completed_run_name
    recording_metrics.record_run_failed.assert_not_called()


def test_vespa_feeder_records_a_failed_run(
    monkeypatch, prefect_db, summary_artifacts, recording_metrics
):
    """A run that loses records is a failed run, not a completed one."""
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(
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
        ),
    )

    with pytest.raises(feeder.VespaFeederFailed):
        _run_vespa_feeder(
            s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
        )

    recording_metrics.record_run_failed.assert_called_once()
    failed_deployment, failed_run_name = (
        recording_metrics.record_run_failed.call_args.args
    )
    assert failed_deployment == "local"
    assert failed_run_name
    recording_metrics.record_run_completed.assert_not_called()
    recording_metrics.record_run_duration.assert_called_once()


def test_vespa_feeder_sets_the_feed_stats_the_slack_hook_reads(
    monkeypatch, prefect_db, summary_artifacts, recording_metrics
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
        _feed_batch_returning(
            _feed_result("one.jsonl", ok=10),
            _feed_result("two.jsonl", ok=5),
        ),
    )

    _run_vespa_feeder(
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
    monkeypatch, prefect_db, summary_artifacts, recording_metrics, telemetry_calls
):
    """
    Order matters.

    force_flush exports metrics and logs with a bounded timeout and a logged
    warning, then shutdown exports the spans nothing else flushes.
    """
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(_feed_result("one.jsonl")),
    )

    _run_vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    assert telemetry_calls == ["force_flush", "shutdown"]


def test_vespa_feeder_closes_the_run_span_before_shutting_telemetry_down(
    monkeypatch, prefect_db, summary_artifacts, recording_metrics
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

    # The feeder's OWN span, not `get_current_span()`: this runs inside a real
    # flow run, whose Prefect-opened span is still current (and still
    # recording) at shutdown. That outer span is Prefect's to close, so
    # sampling the current span would assert on the wrong one.
    feeder_spans = []
    start_span = feeder.tracer.start_as_current_span

    @contextmanager
    def _capture_feeder_span(name, *args, **kwargs):
        with start_span(name, *args, **kwargs) as span:
            if name == "vespa_feeder":
                feeder_spans.append(span)
            yield span

    monkeypatch.setattr(feeder.tracer, "start_as_current_span", _capture_feeder_span)

    # Sampled at the moment shutdown runs, not afterwards: the span ends either
    # way once vespa_feeder returns, so a span object kept for later always
    # looks closed.
    recording_at_shutdown: list[bool] = []

    def _record_span_state() -> None:
        recording_at_shutdown.extend(span.is_recording() for span in feeder_spans)

    monkeypatch.setattr(feeder, "force_flush", lambda: None)
    monkeypatch.setattr(feeder, "shutdown", _record_span_state)

    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(_feed_result("one.jsonl")),
    )

    _run_vespa_feeder(
        s3_bucket="bucket", s3_prefix="prefix/", s3_export_prefix="x", batch_size=1
    )

    # The run span is no longer recording when shutdown runs, so it has
    # already ended and cannot be dropped.
    assert recording_at_shutdown == [False]


def test_vespa_feeder_flushes_telemetry_when_the_run_fails(
    monkeypatch, prefect_db, summary_artifacts, recording_metrics, telemetry_calls
):
    """A failed run is exactly when the metrics matter most."""
    monkeypatch.setattr(feeder, "list_s3_keys", lambda bucket, prefix: ["a"])  # noqa: ARG005
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(RuntimeError("HeadObject: Not Found")),
    )

    with pytest.raises(feeder.VespaFeederFailed):
        _run_vespa_feeder(
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
    prefect_db,
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
    feed_batch_calls: list[dict] = []
    monkeypatch.setattr(
        feeder,
        "feed_batch",
        _feed_batch_returning(
            _feed_result("one.jsonl"), record_calls_in=feed_batch_calls
        ),
    )

    _run_vespa_feeder(
        s3_bucket="bucket",
        s3_prefix=s3_prefix,
        s3_export_prefix=s3_export_prefix,
        batch_size=1,
    )

    assert bool(resolved) is expected_resolved
    assert [call["batched_s3_keys"] for call in feed_batch_calls] == [(expected_fed,)]
