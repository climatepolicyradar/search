"""
Shared engine behind every vespa-feeder.

flow, per batch of S3 keys:
- download the files from S3
- optionally derive data from their records
- feed them to Vespa via the `vespa feed` CLI.

Domain-specific flows (labels_flow.py, documents_flow.py, passages_flow.py)
import `vespa_feeder` and compose it with their own S3 source and (if any)
deriver function. Nothing in this module is domain-specific.
"""

import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from itertools import batched
from pathlib import Path
from types import FrameType

import orjson
from errors import (
    BatchAbandoned,
    FeedResult,
    VespaError,
    VespaFeedError,
    VespaFeedResponse,
    VespaResponseError,
)
from prefect.artifacts import create_markdown_artifact
from prefect.cache_policies import NO_CACHE
from prefect.client.schemas.objects import State
from prefect.exceptions import MissingContextError
from prefect.futures import PrefectFuture
from prefect.runtime import deployment, flow_run
from prefect.states import Failed
from run_summary import (
    _build_failure_message,
    _build_run_summary_markdown,
    _parse_failed_documents,
)
from s3 import (
    delete_materialised_s3_files,
    get_latest_s3_export_prefix,
    get_ssm_parameter,
    list_s3_keys,
    materialise_derived_files,
    materialise_s3_files,
)
from telemetry import (
    feeder_metrics,
    force_flush,
    set_feed_stats,
    shutdown,
    trace,
    tracer,
)

from prefect import get_run_logger, task

logger = logging.getLogger(__name__)

# What `get_run_logger()` hands back inside a run context.
LoggerAdapter = logging.LoggerAdapter[logging.Logger]

# Per-subprocess connection pool size, passed to `vespa feed --connections` in
# feed_derived_files. Paired with the flow's own ThreadPoolTaskRunner(
# max_workers=N) - see the submit loop in vespa_feeder: total concurrent
# connections to Vespa is that max_workers * _DEFAULT_CONNECTIONS. Benchmarking
# (8x2 vs 4x4, same total connection budget) found 8x2 ~15% faster, so tune
# both together rather than either in isolation.
_DEFAULT_CONNECTIONS = 2


# How many S3 keys each materialise/feed/delete chain handles at once.
DEFAULT_BATCH_SIZE = 10

# 1 feeds every file list_s3_keys discovers. Lower it to benchmark against a
# subset of a source without needing a separate S3 prefix; production flows
# should leave it alone.
DEFAULT_SAMPLE_RATE = 1.0

# How long one batch's `vespa feed` subprocess may run before we give up on it.
#
# Flat per batch, not per file. Measured over 24h of production runs (Tempo
# spans, 2026-11-03/04): passages p50 72s, p90 227s, p99 654s, max 2324s
# (38.7 min); documents max 275s; labels 17s. File count predicted nothing --
# the 38.7 min outlier held 10 files, exactly like the 39 batches in the same
# run that finished under 18 min -- so scaling by it added no information.
#
# Scaling by file count was also wrong in both directions: a 10-file batch got
# 50 min, but the passages final batch (4 files) got 20 min and every labels
# run (1 file) got 5 min, both under the 38.7 min we have actually observed.
#
# 45 min clears the worst batch we have actually observed, with ~16% headroom,
# while still bounding a wedged feed. Deliberately not tighter: until FUS-892
# adds bounded retries, a timed-out batch loses its records, so failing a batch
# that would have completed is a real cost.
_VESPA_FEED_TIMEOUT_SECONDS = 45 * 60

# How long the drain waits for any one batch before giving up on it.
#
# Sized against one batch, which is itself capped at
# `_VESPA_FEED_TIMEOUT_SECONDS` (45 min) plus `_S3_DOWNLOAD_TIMEOUT_SECONDS`
# (5 min). 90 min is ~1.8x that ceiling, so a healthy batch never trips it
# however slow it is, while a wedged one is abandoned rather than hanging the
# run.
#
# On its own this does NOT bound the run. `concurrent.futures` measures a
# timeout from the call, not from submission, so the allowance restarts for
# every batch: with all workers wedged, N batches each wait the full 90 min.
# At the passages flow's 589 batches that is 36 days - worse than the 52h hang
# it was meant to fix. `_DRAIN_TIMEOUT_SECONDS` is what actually bounds the
# run; this bounds a single wait within it.
_BATCH_RESULT_TIMEOUT_SECONDS = 90 * 60

# How long a whole run may take, as both the flow's `timeout_seconds` and the
# drain's own budget. Every feeder flow passes this to `@flow`.
#
# One constant for the two because they are two expressions of the same
# deadline, and they only work as a pair: Prefect raises `timeout_seconds` via
# SIGALRM, delivered only to the main thread, which spends the drain blocked
# in `.result()` - so it does not fire when it is most needed. The drain
# budget is what actually stops the run at this point. Setting one without the
# other gives a bound that either never fires or fires early, which is how run
# 06aec620 sat for 52h under a 20h flow timeout.
#
# Sized to bound a hung run inside the 24h gap to the next schedule, so it
# fails rather than hanging and queueing tomorrow's run behind it. The longest
# passages run observed is ~6h, so it never fires in normal operation.
RUN_TIMEOUT_SECONDS = 20 * 60 * 60

# How long the whole drain may take, across every batch.
#
# The real bound on the run. Held as a deadline rather than a per-call
# allowance so that wedged batches cannot accumulate: each `.result()` gets
# whatever is left of the budget, so N wedged batches cost one budget between
# them rather than N.
#
# A run that trips it has already lost its deadline; the point is that it
# reports and exits instead of sitting for days.
_DRAIN_TIMEOUT_SECONDS = RUN_TIMEOUT_SECONDS


# we store all `vespa feed` processes in this set to be able to
# terminate them on SIGTERM of the main thread
_vespa_feed_processes: set[subprocess.Popen] = set()
# Guards `add`/`discard`/read on `_vespa_feed_processes`.
#
# Reentrant, because `_terminate_vespa_feed_processes` takes it from inside a
# signal handler. A handler runs on the main thread between bytecodes, so if
# SIGTERM lands while that thread already holds this lock - it is taken in the
# drain's `finally` and around every spawn - a plain Lock would block the
# handler on a lock only the interrupted frame can release, hanging the process
# for good. An RLock is re-acquirable by its owning thread, so the handler
# proceeds.
_vespa_feed_processes_lock = threading.RLock()
# we store this value to be able to run it on `_terminate_vespa_feed_processes` to avoid
# swallowing any `TerminationSignals`
_main_thread_sigterm_handler: Callable | int | None = None


def _terminate_vespa_feed_processes(signum: int, frame: FrameType | None) -> None:
    with _vespa_feed_processes_lock:
        processes = list(_vespa_feed_processes)
    # A module-level logger rather than get_run_logger(): this runs inside a
    # signal handler, which can re-enter whatever the interrupted frame held.
    logger.warning(
        f"Received signal {signum}, terminating {len(processes)} "
        "in-flight vespa feed process(es)"
    )
    for process in processes:
        process.terminate()

    # Hand back to the handler we displaced - under a flow run that is
    # Prefect's own SIGTERM bridge, which raises TerminationSignal and drives
    # the run to Cancelled. Returning here instead swallows the signal: the
    # flow keeps submitting batches and never reports the cancellation.
    if callable(_main_thread_sigterm_handler):
        _main_thread_sigterm_handler(signum, frame)


def _terminate_in_flight_feeds() -> int:
    """
    Terminate every `vespa feed` child still running, and say how many.

    Snapshots under the lock and terminates outside it, so a worker finishing
    normally can still `discard` itself while this runs. `terminate()` on a
    process that has already exited is a no-op, so racing one is harmless.
    """
    with _vespa_feed_processes_lock:
        in_flight = list(_vespa_feed_processes)
    for in_flight_process in in_flight:
        in_flight_process.terminate()
    return len(in_flight)


def _terminate_vespa_feed_processes_on_sigterm_handler() -> None:
    """
    Runs `_terminate_vespa_feed_processes` on the main threads `SIGTERM`.

    This avoids any unhandled `_vespa_feed_processes`.

    Calling this from vespa_feeder rather than at import time keeps it in
    the Prefect process running the flow.
    """

    global _main_thread_sigterm_handler
    # The conditional guards as signal.signal() raises ValueError outside
    # the main thread.
    #
    # Prefect's runner can re-import this module from a worker thread (e.g. to resolve
    # on_crashed hooks after the flow run's own process has already died).
    if threading.current_thread() is threading.main_thread():
        _main_thread_sigterm_handler = signal.signal(
            signal.SIGTERM, _terminate_vespa_feed_processes
        )


@tracer.start_as_current_span("feed_derived_files")
def feed_derived_files(
    materialised_derived_files: list[Path],
    endpoint: str,
    application: str,
    connections: int = _DEFAULT_CONNECTIONS,
    feed_timeout_seconds: int = _VESPA_FEED_TIMEOUT_SECONDS,
) -> FeedResult:
    input_count = sum(
        1
        for materialised_derived_file in materialised_derived_files
        for line in materialised_derived_file.open("rb")
        if line.strip()
    )

    # Popen rather than subprocess.run so _terminate_vespa_feed_processes has
    # something to terminate: run() owns its child privately, and this call is
    # on a task runner worker thread, where a signal handler never runs.
    #
    # Do not pass --verbose, which logs every successful operation as well as every
    # failed operation to stderr resulting in ~1GB of unused logs.
    with subprocess.Popen(
        [
            "vespa",
            "feed",
            *[
                str(materialised_derived_file)
                for materialised_derived_file in materialised_derived_files
            ],
            "--target",
            endpoint,
            "--application",
            application,
            "--connections",
            str(connections),
            "--inflight",
            "0",
        ],
        env=os.environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        with _vespa_feed_processes_lock:
            _vespa_feed_processes.add(process)
        try:
            stdout, stderr = process.communicate(timeout=feed_timeout_seconds)
        except BaseException:
            # What subprocess.run does too: never leave the child running when
            # the call that owns it is unwinding. Popen.__exit__ then closes
            # the pipes and reaps it.
            process.kill()
            raise
        finally:
            with _vespa_feed_processes_lock:
                _vespa_feed_processes.discard(process)

    # replicates the `check=True` from `subprocess.run()`
    # as we use `Popen` above.
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, process.args, output=stdout, stderr=stderr
        )

    response = VespaFeedResponse.model_validate(orjson.loads(stdout))
    throttled_count = response.http_response_code_counts.get("429", 0)
    other_http_error_count = response.http_response_error_count - throttled_count
    not_ok_count = response.feeder_operation_count - response.feeder_ok_count
    failed_documents = _parse_failed_documents(stderr)

    errors: list[VespaError] = []
    if not_ok_count > 0:
        if response.feeder_error_count > 0:
            errors.append(
                VespaFeedError(
                    feeder_error_count=response.feeder_error_count,
                    failed_documents=failed_documents,
                )
            )
        errors.append(
            VespaResponseError(
                ok_count=response.feeder_ok_count,
                operation_count=response.feeder_operation_count,
                throttled_count=throttled_count,
                other_http_error_count=other_http_error_count,
                failed_documents=failed_documents,
            )
        )

    return FeedResult(
        feed_paths=materialised_derived_files,
        input_count=input_count,
        operation_count=response.feeder_operation_count,
        ok_count=response.feeder_ok_count,
        feeder_error_count=response.feeder_error_count,
        throttled_count=throttled_count,
        other_http_error_count=other_http_error_count,
        errors=errors,
    )


@task(cache_policy=NO_CACHE)
@tracer.start_as_current_span("feed_batch")
def feed_batch(
    batch_number: int,
    batch_count: int,
    endpoint: str,
    application: str,
    connections: int,
    feed_timeout_seconds: int,
    s3_bucket: str,
    batched_s3_keys: tuple[str, ...],
    derive_data_from_source: Callable[[dict], dict] | None = None,
) -> FeedResult:
    start_time = time.perf_counter()
    deployment_name = deployment.name or "local"
    run_name = flow_run.name or "unknown"

    # Logged here rather than at the submit site so the line marks work
    # actually starting: a worker has picked this batch up. The submit loop
    # enqueues every batch in seconds, so a line there tracked nothing.
    #
    # The module logger fallback keeps `feed_batch.fn()` callable outside a
    # run context, which is how the disk and feed behaviour is tested.
    try:
        batch_logger: logging.Logger | LoggerAdapter = get_run_logger()
    except MissingContextError:
        batch_logger = logger
    batch_logger.info(
        f"Feeding batch {batch_number}/{batch_count} ({len(batched_s3_keys)} files)"
    )

    try:
        # All files from s3 and derived are stored in the `TemporaryDirectory`
        # and deleted when the `with` block exits via `TemporaryDirectory.__exit__`.
        with tempfile.TemporaryDirectory(prefix="vespa-feeder-") as materialise_dir:
            materialised_s3_files = materialise_s3_files(
                bucket=s3_bucket,
                batched_s3_keys=list(batched_s3_keys),
                materialise_dir=Path(materialise_dir),
            )

            materialised_derived_files = materialise_derived_files(
                materialised_s3_files=materialised_s3_files,
                derive_data_from_source=derive_data_from_source,
            )

            # Delete the downloaded sources now that the derived copies exist.
            # Without this a batch holds both copies of every record at once,
            # roughly doubling its peak disk use.
            delete_materialised_s3_files(materialised_s3_files=materialised_s3_files)

            feed_result = feed_derived_files(
                materialised_derived_files=materialised_derived_files,
                endpoint=endpoint,
                application=application,
                connections=connections,
                feed_timeout_seconds=feed_timeout_seconds,
            )

        # operation - ok is the only count that means records were actually
        # lost. feeder/throttled/other-HTTP errors are retry attempts that
        # mostly self-heal, so they must not inflate this.
        feeder_metrics.record_feed_stats(
            input_count=feed_result.input_count,
            ok_count=feed_result.ok_count,
            total_errors=feed_result.operation_count - feed_result.ok_count,
            deployment_name=deployment_name,
            run_name=run_name,
        )

        # Replaces the `vespa feed stats:` log line `9dcb83b` deleted, which
        # the dashboard's Runs table still parsed.
        feeder_metrics.record_retry_stats(
            feeder_error_count=feed_result.feeder_error_count,
            throttled_count=feed_result.throttled_count,
            other_http_error_count=feed_result.other_http_error_count,
            file_count=len(feed_result.feed_paths),
            deployment_name=deployment_name,
            run_name=run_name,
        )

        # Not in the `finally` - a batch that raised fed nothing, so counting
        # it would overstate how far a crashed run got.
        feeder_metrics.record_batch_completed(
            deployment_name=deployment_name,
            run_name=run_name,
        )

        return feed_result
    finally:
        feeder_metrics.record_task_duration(
            task_name="feed_batch",
            duration_s=time.perf_counter() - start_time,
            deployment_name=deployment_name,
        )


def vespa_feeder(
    s3_bucket: str,
    s3_prefix: str,
    s3_export_prefix: str | None = None,
    derive_data_from_source: Callable[[dict], dict] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    connections: int = _DEFAULT_CONNECTIONS,
    feed_timeout_seconds: int = _VESPA_FEED_TIMEOUT_SECONDS,
    sample_rate: float = DEFAULT_SAMPLE_RATE,
    batch_result_timeout_seconds: float = _BATCH_RESULT_TIMEOUT_SECONDS,
    drain_timeout_seconds: float = _DRAIN_TIMEOUT_SECONDS,
) -> State | None:
    try:
        with tracer.start_as_current_span("vespa_feeder"):
            run_logger = get_run_logger()
            start_time = time.perf_counter()
            deployment_name = deployment.name or "local"
            run_name = flow_run.name or "unknown"
            # this ensures we terminate any `vespa feed` processes
            # spawned from `feed_derived_files`
            _terminate_vespa_feed_processes_on_sigterm_handler()

            if not 0 < sample_rate <= 1:
                raise ValueError(f"sample_rate must be in (0, 1], got {sample_rate}")

            endpoint = get_ssm_parameter(name="/search/vespa/endpoint")
            application = get_ssm_parameter(name="/search/vespa/application")
            # This is read by Vespa CLI
            # @see: https://docs.vespa.ai/en/security/guide.html#use-endpoints
            os.environ["VESPA_CLI_DATA_PLANE_TOKEN"] = get_ssm_parameter(
                name="/search/vespa/write_token"
            )

            s3_export_prefix_pinned = s3_export_prefix is not None

            if s3_prefix.endswith(".jsonl"):
                # @related: LABEL_RELATIONSHIPS_DO_NOT_EXIST
                s3_keys = [s3_prefix]
                s3_prefix_full = s3_prefix
            else:
                if s3_export_prefix is None:
                    s3_export_prefix = get_latest_s3_export_prefix(
                        bucket=s3_bucket, prefix=s3_prefix
                    )
                s3_prefix_full = f"{s3_prefix}{s3_export_prefix}"
                s3_keys = list_s3_keys(bucket=s3_bucket, prefix=s3_prefix_full)

            if sample_rate < 1:
                # Every nth key from the sorted listing, rather than the first n. Both
                # are deterministic - so every A/B variant feeds the identical subset -
                # but a stride is positionally unbiased, which matters if whatever
                # produced the files varies along the ordering.
                s3_keys = s3_keys[:: round(1 / sample_rate)]

            # Log and trace before we get going
            run_logger.info(
                f"Feeding {len(s3_keys)} files from s3://{s3_bucket}/{s3_prefix_full} "
                f"in batches of {batch_size} (sample_rate={sample_rate})"
            )
            trace.get_current_span().set_attributes(
                {
                    "s3_bucket": s3_bucket,
                    "s3_prefix": s3_prefix,
                    "s3_export_prefix": s3_export_prefix or "",
                    "s3_export_prefix_pinned": s3_export_prefix_pinned,
                    "batch_size": batch_size,
                    "sample_rate": sample_rate,
                    "connections": connections,
                    "s3_keys_len": len(s3_keys),
                }
            )

            s3_key_batches = list(batched(s3_keys, batch_size))

            # Before the submit loop so it survives a crash, giving the
            # per-batch counters a denominator to be read against.
            feeder_metrics.record_batches_expected(
                batch_count=len(s3_key_batches),
                deployment_name=deployment_name,
                run_name=run_name,
            )

            feed_results_futures: list[PrefectFuture[FeedResult]] = []
            for batch_number, batched_s3_keys in enumerate(s3_key_batches, start=1):
                feed_results_futures.append(
                    feed_batch.submit(
                        batch_number=batch_number,
                        batch_count=len(s3_key_batches),
                        endpoint=endpoint,
                        application=application,
                        connections=connections,
                        feed_timeout_seconds=feed_timeout_seconds,
                        s3_bucket=s3_bucket,
                        batched_s3_keys=batched_s3_keys,
                        derive_data_from_source=derive_data_from_source,
                    )
                )

            # Deliberately one line for the whole loop, not one per batch.
            # `submit()` only enqueues - the loop runs to completion in seconds,
            # long before the first batch is fed - so a per-batch line here
            # reads as progress while reporting none. The per-batch line is
            # logged by `feed_batch` itself, once a worker has picked it up.
            run_logger.info(
                f"Queued {len(s3_key_batches)} batch(es) onto the task runner; "
                f"{len(s3_keys)} file(s) total"
            )

            # resolve feed_results_futures and raise on any exceptions
            feed_results: list[FeedResult] = []
            feed_results_exceptions: list[BaseException] = []

            # the finally is for a cancel mid-drain: `raise_on_failure=False` means no
            # batch raises here, so it is SIGTERM that would otherwise lose the summary.
            drained = False
            # Bounds the drain as a whole, so wedged batches cannot accumulate.
            # This is the guard the flow-level `timeout_seconds` cannot be:
            # Prefect raises that via SIGALRM, delivered only to the main
            # thread, which spends the drain blocked in `.result()`. In run
            # 06aec620 all 8 workers wedged, the 20h timeout never fired, and
            # the run sat for 52h until cancelled by hand.
            drain_deadline = time.monotonic() + drain_timeout_seconds
            try:
                for batch_number, feed_result_future in enumerate(
                    feed_results_futures, start=1
                ):
                    # Whatever is left of the run budget, capped at the
                    # per-batch bound. Taking the lower of the two is what
                    # stops N wedged batches costing N x the per-batch wait:
                    # the budget is spent once across the drain, not reset by
                    # each call the way `.result(timeout=...)` alone would.
                    remaining = drain_deadline - time.monotonic()
                    if remaining <= 0:
                        # Every remaining batch is abandoned unwaited - there is
                        # no budget left to tell a wedged one from a slow one.
                        abandoned = len(feed_results_futures) - batch_number + 1
                        run_logger.error(
                            f"Drain exceeded {drain_timeout_seconds:.0f}s with "
                            f"{abandoned} batch(es) unresolved; abandoning them."
                        )
                        feed_results_exceptions.extend(
                            BatchAbandoned(
                                f"Batch {abandoned_number}/{len(feed_results_futures)} "
                                f"abandoned: drain exceeded "
                                f"{drain_timeout_seconds:.0f}s before it was waited on"
                            )
                            for abandoned_number in range(
                                batch_number, len(feed_results_futures) + 1
                            )
                        )
                        # The drain's `finally` terminates these too, but it is
                        # reached via the same path either way - keeping the
                        # call here means both abandonment paths read alike.
                        _terminate_in_flight_feeds()
                        break

                    # we do not raise to be able to aggregate and report on this in the markdown artifact.
                    try:
                        feed_result = feed_result_future.result(
                            timeout=min(remaining, batch_result_timeout_seconds),
                            raise_on_failure=False,
                        )
                    except TimeoutError as timeout_error:
                        run_logger.error(
                            f"Batch {batch_number}/{len(feed_results_futures)} "
                            f"timed out: {timeout_error}"
                        )
                        feed_results_exceptions.append(
                            BatchAbandoned(
                                f"Batch {batch_number}/{len(feed_results_futures)} "
                                f"abandoned: {timeout_error}"
                            )
                        )
                        # Stop the abandoned batch writing, rather than leaving
                        # it to the drain's `finally`. `continue` gives up the
                        # wait, not the work: the worker stays in
                        # `communicate()` and its child keeps feeding Vespa for
                        # however long the rest of the drain takes - records
                        # landing after the run has already reported them
                        # unaccounted for. Terminating here closes that window.
                        #
                        # This can also catch a healthy batch that happens to
                        # be in flight, which is the deliberate trade: by the
                        # time a batch has blown a 90 min bound the run is
                        # being abandoned anyway, and a terminated feed is
                        # re-fed, while an untracked one corrupts the accounting.
                        terminated = _terminate_in_flight_feeds()
                        if terminated:
                            run_logger.warning(
                                f"Terminated {terminated} in-flight vespa feed "
                                "process(es) after abandoning a batch."
                            )
                        continue

                    if isinstance(feed_result, BaseException):
                        # exc_info so the traceback survives. The run ends in a
                        # Failed state rather than by raising, so this is the
                        # only place the stack is recorded.
                        run_logger.error(
                            f"Batch raised {type(feed_result).__name__}: {feed_result}",
                            exc_info=feed_result,
                        )
                        feed_results_exceptions.append(feed_result)
                        continue

                    feed_results.append(feed_result)
                drained = True
            finally:
                # A flow-level timeout or a cancel arrives on this thread, but
                # worker threads blocked in `communicate()` never see it.
                # Without this, the run ends while orphaned `vespa feed`
                # children keep writing to Vespa until the container dies. We
                # hook the `finally` rather than installing a SIGALRM handler,
                # because Prefect owns that signal and competing for it would
                # break its cancel scope.
                _terminate_in_flight_feeds()

                # we then get the known failures from the vespa FeedResult
                feed_results_errors = [
                    result for result in feed_results if result.errors
                ]

                # The same totals the artifact reports, so the Slack notification and
                # the artifact cannot disagree.
                total_input = sum(result.input_count for result in feed_results)
                total_operation = sum(result.operation_count for result in feed_results)
                total_ok = sum(result.ok_count for result in feed_results)
                run_failed = bool(feed_results_errors or feed_results_exceptions)

                # publish the artifact in Prefect
                # Lost on a SIGKILL, so its absence means the run did not
                # finish, never that it fed nothing. See
                # docs/run-reporting-and-crashes.md.
                create_markdown_artifact(
                    key="vespa-feeder-run-summary",
                    markdown=_build_run_summary_markdown(
                        feed_results, feed_results_exceptions
                    ),
                    description="Aggregate summary of the vespa-feeder run across all files",
                )

                set_feed_stats(
                    input_count=total_input,
                    ok_count=total_ok,
                    total_errors=total_operation - total_ok,
                )

                # Recorded unconditionally: a run that was cancelled still
                # consumed that time, and `feed_batch` sets the same precedent
                # by timing a batch that raised.
                feeder_metrics.record_run_duration(
                    time.perf_counter() - start_time, deployment_name, run_name
                )

                # A cancel mid-drain is neither outcome. Counting it completed
                # makes a run stopped after 1 of 2 batches look identical to a
                # full success - which is rubbish, because it makes it harder
                # to calculate a success rate using runs.completed and
                # runs.failed. Counting it failed would also be wrong and
                # would alert despite it being a deliberate own decision, so 
                # it is recorded as neither.
                if not drained:
                    run_logger.warning(
                        "Run did not finish draining its batches, so it is "
                        "recorded as neither completed nor failed."
                    )
                elif run_failed:
                    feeder_metrics.record_run_failed(deployment_name, run_name)
                else:
                    feeder_metrics.record_run_completed(deployment_name, run_name)

            if feed_results_errors or feed_results_exceptions:
                # Failed rather than raised. Losing records is an outcome of
                # the feed, not an error in running it, and raising wrapped
                # the message in "encountered an exception" plus a traceback
                # pointing at this line - which says nothing about the cause.
                # Batches that raised are logged with their tracebacks above.
                return Failed(
                    message=_build_failure_message(
                        feed_results=feed_results,
                        feed_results_errors=feed_results_errors,
                        feed_results_exceptions=feed_results_exceptions,
                        records_lost=total_operation - total_ok,
                        run_ui_url=flow_run.ui_url,
                    )
                )
    finally:
        # Outside the span, and outside the inner finally: shutdown() tears
        # down the tracer provider, and any span still open when it runs is
        # dropped - so the span has to close first or the root vespa_feeder
        # span is lost on every run. v1 got this ordering from an explicit
        # `with`; the decorator form hid it. force_flush() first for its
        # bounded timeout and logged warning, which shutdown() swallows; it
        # flushes metrics and logs but never traces, so both are needed.
        force_flush()
        shutdown()
