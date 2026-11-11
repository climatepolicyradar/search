"""
Table-driven tests for the run summary artifact's arithmetic.

This artifact is what gets read when a feed partially fails, so its numbers
have to mean what they say. Four bugs survived in it undetected because
nothing exercised `_build_run_summary_markdown` directly: every test fed it
one file per batch, where a batch count and a file count look identical.
"""

from pathlib import Path

import pytest
import run_summary
import vespa_feeder as feeder


def _result(
    *,
    files: int = 1,
    input_count: int = 10,
    operation_count: int = 10,
    ok_count: int = 10,
    feeder_error_count: int = 0,
    throttled_count: int = 0,
    other_http_error_count: int = 0,
    errors: list | None = None,
    prefix: str = "batch",
) -> feeder.FeedResult:
    return feeder.FeedResult(
        feed_paths=[Path(f"{prefix}-{n}.jsonl") for n in range(files)],
        input_count=input_count,
        operation_count=operation_count,
        ok_count=ok_count,
        feeder_error_count=feeder_error_count,
        throttled_count=throttled_count,
        other_http_error_count=other_http_error_count,
        errors=errors or [],
    )


def _row(markdown: str, label: str) -> str:
    """The value cell of the named row, so a test asserts on one number."""
    for line in markdown.splitlines():
        if line.startswith(f"| {label} |"):
            return line.split("|")[2].strip()
    raise AssertionError(f"no {label!r} row in:\n{markdown}")


def test_files_processed_counts_files_rather_than_batches():
    """
    A `FeedResult` is one batch of `batch_size` files, not one file.

    FUS-752 was triaged from "Files processed 572", which was really 572
    batches of 10 - roughly 5,720 files. Off by an order of magnitude in the
    number used to judge how much of a run succeeded.
    """
    markdown = run_summary._build_run_summary_markdown(
        [_result(files=10), _result(files=10), _result(files=4)], []
    )

    assert _row(markdown, "Files processed") == "24"
    assert _row(markdown, "Batches") == "3"


def test_a_raised_batch_is_reported_as_unaccounted_for():
    """
    Records lost to a raised batch must not read as a clean run.

    A raised batch produces no `FeedResult`, so it adds nothing to
    Operations or OK - and therefore nothing to Missing. A run could lose
    ten files' worth of records and still show `Missing: 0` with otherwise
    clean totals.
    """
    markdown = run_summary._build_run_summary_markdown(
        [_result(files=10)], [RuntimeError("HeadObject: Not Found")]
    )

    assert _row(markdown, "Batches that raised") == "1"
    assert _row(markdown, "**Unaccounted for (1 batch(es) raised)**") == "**unknown**"
    assert "not in the totals above" in markdown
    assert "| `RuntimeError` | HeadObject: Not Found |" in markdown


def test_a_clean_run_claims_nothing_is_unaccounted_for():
    """The unaccounted-for row is noise on a run where every batch reported."""
    markdown = run_summary._build_run_summary_markdown([_result(files=10)], [])

    assert "Unaccounted for" not in markdown
    assert "not in the totals above" not in markdown
    assert "All files indexed successfully" in markdown


def test_failed_documents_are_listed_once_per_doc_id():
    """
    Both error types are built from the same parsed stderr.

    A batch that loses records to a transport failure carries the same
    `failed_documents` on its `VespaFeedError` and its `VespaResponseError`,
    so concatenating them listed every doc id twice and inflated "+N more".
    """
    failed_documents = [
        run_summary.FailedDocument(doc_id=f"id:doc::{n}", error="status 500")
        for n in range(5)
    ]
    result = _result(
        files=10,
        operation_count=10,
        ok_count=5,
        errors=[
            feeder.VespaFeedError(
                feeder_error_count=5, failed_documents=failed_documents
            ),
            feeder.VespaResponseError(
                ok_count=5,
                operation_count=10,
                throttled_count=0,
                other_http_error_count=5,
                failed_documents=failed_documents,
            ),
        ],
    )

    markdown = run_summary._build_run_summary_markdown([result], [])

    assert markdown.count("`id:doc::0`") == 1
    # Five unique docs, three sampled, so two remain - not seven.
    assert "(+2 more)" in markdown


def test_a_failing_batch_is_not_counted_as_both_processed_and_failed():
    """
    Failures are derived from the results, not passed alongside them.

    The caller passed `feed_results` and a subset of it, so a failing batch
    appeared in both rows and the run looked like it had more batches than
    it ran.
    """
    markdown = run_summary._build_run_summary_markdown(
        [
            _result(files=10, prefix="ok"),
            _result(
                files=10,
                operation_count=10,
                ok_count=9,
                prefix="bad",
                errors=[
                    feeder.VespaResponseError(
                        ok_count=9,
                        operation_count=10,
                        throttled_count=0,
                        other_http_error_count=1,
                        failed_documents=[
                            run_summary.FailedDocument(
                                doc_id="id:doc::1", error="status 500"
                            )
                        ],
                    )
                ],
            ),
        ],
        [],
    )

    assert _row(markdown, "Batches") == "2"
    assert _row(markdown, "Batches with lost records") == "1"
    assert _row(markdown, "Files processed") == "20"
    assert "1/2 batch(es) failed" in markdown


@pytest.mark.parametrize(
    ("results", "expected_rate"),
    [
        pytest.param([], "0.00%", id="no-results-does-not-divide-by-zero"),
        pytest.param(
            [_result(operation_count=100, ok_count=100, throttled_count=25)],
            "25.00%",
            id="throttled-over-all-operations",
        ),
    ],
)
def test_throttle_rate_divides_by_every_operation_reported(results, expected_rate):
    """The denominator is every operation, failing batches included."""
    assert _row(run_summary._build_run_summary_markdown(results, []), "Throttle rate") == (
        expected_rate
    )


def test_throttle_rate_includes_operations_from_failing_batches():
    """
    A failing batch's operations belong in the denominator.

    Dividing by successful batches only overstated the rate whenever a
    batch failed, which is exactly when the artifact is being read.
    """
    throttled = _result(
        operation_count=100, ok_count=100, throttled_count=50, prefix="ok"
    )
    failing = _result(
        operation_count=100,
        ok_count=99,
        prefix="bad",
        errors=[
            feeder.VespaResponseError(
                ok_count=99,
                operation_count=100,
                throttled_count=0,
                other_http_error_count=1,
                failed_documents=[],
            )
        ],
    )

    markdown = run_summary._build_run_summary_markdown([throttled, failing], [])

    # 50 throttled over 200 operations, not over the 100 that went well.
    assert _row(markdown, "Throttle rate") == "25.00%"


def test_a_mixed_run_reports_every_category_at_once():
    """A run can succeed, lose records and raise all at the same time."""
    failing = _result(
        files=10,
        input_count=10,
        operation_count=10,
        ok_count=7,
        prefix="bad",
        errors=[
            feeder.VespaResponseError(
                ok_count=7,
                operation_count=10,
                throttled_count=0,
                other_http_error_count=3,
                failed_documents=[
                    run_summary.FailedDocument(doc_id="id:doc::1", error="status 500")
                ],
            )
        ],
    )

    markdown = run_summary._build_run_summary_markdown(
        [_result(files=10, prefix="ok"), failing], [RuntimeError("boom")]
    )

    assert _row(markdown, "Files processed") == "20"
    assert _row(markdown, "Batches") == "3"
    assert _row(markdown, "Batches with lost records") == "1"
    assert _row(markdown, "Batches that raised") == "1"
    assert _row(markdown, "Operations") == "20"
    assert _row(markdown, "OK") == "17"
    assert _row(markdown, "**Missing (not recovered after retries)**") == "**3**"
    assert "2/3 batch(es) failed" in markdown


def _failing_result() -> feeder.FeedResult:
    return _result(files=2, operation_count=10, ok_count=6, errors=["lost"])


def test_failure_message_leads_with_the_records_lost() -> None:
    """Records lost is the figure that matters; batches and files locate it."""
    lost = _failing_result()

    message = run_summary._build_failure_message(
        feed_results=[lost, _result()],
        feed_results_errors=[lost],
        feed_results_exceptions=[],
        records_lost=1200,
    )

    assert "lost 1,200 record(s) across 1/2 batch(es) (2 file(s))" in message


def test_failure_message_names_the_exception_type() -> None:
    """The cause should be readable without opening the logs."""
    message = run_summary._build_failure_message(
        feed_results=[_result()],
        feed_results_errors=[],
        feed_results_exceptions=[RuntimeError("HeadObject: Not Found")],
        records_lost=0,
    )

    assert "1/2 batch(es) raised (RuntimeError)" in message


def test_failure_message_links_to_the_run_when_it_has_a_url() -> None:
    lost = _failing_result()

    message = run_summary._build_failure_message(
        feed_results=[lost],
        feed_results_errors=[lost],
        feed_results_exceptions=[],
        records_lost=4,
        run_ui_url="https://app.prefect.cloud/account/a/workspace/w/flow-runs/flow-run/r",
    )

    assert (
        "https://app.prefect.cloud/account/a/workspace/w/flow-runs/flow-run/r/artifacts"
        in message
    )


def test_failure_message_names_the_artifact_when_there_is_no_url() -> None:
    """`flow_run.ui_url` is None outside a run context, e.g. a local run."""
    lost = _failing_result()

    message = run_summary._build_failure_message(
        feed_results=[lost],
        feed_results_errors=[lost],
        feed_results_exceptions=[],
        records_lost=4,
    )

    assert "See the vespa-feeder-run-summary artifact" in message
    assert "None" not in message
