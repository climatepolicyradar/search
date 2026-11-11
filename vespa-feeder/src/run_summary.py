"""
The run summary artifact, and the stderr parsing it is built from.

Reporting rather than feeding: how a run's results are turned into the
markdown Prefect publishes, and how `vespa feed`'s stderr is mined for the
documents it gave up on. Split from `vespa_feeder` so the flow module holds
the feeding itself.

`vespa_feeder` re-exports these, so `feeder._build_run_summary_markdown` and
friends keep resolving for the tests that reach for them.
"""

import re

from errors import FailedDocument, FeedResult

# The CLI's `logResult` drops a line only when it is a retry or a success, so
# these survive without `--verbose` - which would log every successful op too,
# meaning ~1GB of stderr on a passages run for nothing we read or used in Grafana.
_GIVING_UP_RE = re.compile(r"^feed: (.+) for put (\S+): giving up", re.MULTILINE)


def _parse_failed_documents(stderr: str) -> list[FailedDocument]:
    return [
        FailedDocument(doc_id=giving_up_match.group(2), error=giving_up_match.group(1))
        for giving_up_match in _GIVING_UP_RE.finditer(stderr)
    ]


def _unique_failed_documents(result: FeedResult) -> list[FailedDocument]:
    """
    Every failed document in a result, each listed once.

    A batch that loses records to a transport failure produces both a
    `VespaFeedError` and a `VespaResponseError`, and both are built from the
    same parsed stderr - so concatenating their `failed_documents` lists the
    same doc id twice and inflates the "+N more" count.
    """
    unique_failed_documents: dict[str, FailedDocument] = {}
    for error in result.errors:
        for failed_document in error.failed_documents:
            unique_failed_documents.setdefault(failed_document.doc_id, failed_document)
    return list(unique_failed_documents.values())


def _build_run_summary_markdown(
    results: list[FeedResult],
    exceptions: list[BaseException],
) -> str:
    """
    Summarise a run: what was fed, what was lost, and what is unaccounted for.

    `results` is every batch that reported back, whether or not it lost
    records. Failures are derived from it rather than passed separately,
    because passing a subset alongside the whole meant a failing batch was
    counted in both the processed and the failed rows.

    A batch that raised never produced a `FeedResult`, so its records cannot
    be counted. They are reported as unaccounted for rather than silently
    omitted: a run could previously lose ten files' worth of records and
    still show `Missing: 0`.
    """
    failures = [result for result in results if result.errors]

    total_files = sum(len(result.feed_paths) for result in results)
    total_input = sum(result.input_count for result in results)
    total_operation = sum(result.operation_count for result in results)
    total_ok = sum(result.ok_count for result in results)
    total_missing = total_operation - total_ok
    total_feeder_errors = sum(result.feeder_error_count for result in results)
    total_throttled = sum(result.throttled_count for result in results)
    total_other_http_errors = sum(result.other_http_error_count for result in results)

    # Denominator is every operation reported by any batch, failing ones
    # included. Excluding failures measured the throttle rate only over the
    # batches that went well.
    throttle_rate = total_throttled / total_operation if total_operation else 0.0

    icon = "🚨" if failures or exceptions else "✅"
    status = (
        f"**{len(failures) + len(exceptions)}/{len(results) + len(exceptions)} "
        "batch(es) failed**"
        if failures or exceptions
        else "**All files indexed successfully**"
    )

    markdown = (
        f"### Vespa Feeder Run Summary\n\n{icon} {status}\n\n"
        "| Metric | Value |\n|---|---|\n"
        f"| Files processed | {total_files} |\n"
        f"| Batches | {len(results) + len(exceptions)} |\n"
        f"| Batches with lost records | {len(failures)} |\n"
        f"| Batches that raised | {len(exceptions)} |\n"
        f"| Input records | {total_input} |\n"
        f"| Operations | {total_operation} |\n"
        f"| OK | {total_ok} |\n"
        f"| **Missing (not recovered after retries)** | **{total_missing}** |\n"
    )

    if exceptions:
        markdown += (
            f"| **Unaccounted for ({len(exceptions)} batch(es) raised)** | "
            "**unknown** |\n"
        )

    markdown += (
        f"| — | — |\n"
        f"| _Transient, self-resolved (no data lost):_ | |\n"
        f"| Transport retries (feeder errors) | {total_feeder_errors} |\n"
        f"| Throttled (429) | {total_throttled} |\n"
        f"| Other non-2xx responses | {total_other_http_errors} |\n"
        f"| Throttle rate | {throttle_rate:.2%} |\n"
    )

    if exceptions:
        markdown += (
            "\nA batch that raised never reported a result, so its records are "
            "not in the totals above: they were neither fed nor counted as "
            "missing. Treat the totals as a lower bound on what was attempted.\n"
        )

    if failures:
        markdown += (
            "\n#### Batches with lost records\n\n"
            "| Files | OK / Operation | Missing | Sample failed documents |\n"
            "|---|---|---|---|\n"
        )
        for result in failures:
            failed_documents = _unique_failed_documents(result)
            sample = "; ".join(
                f"`{failed_document.doc_id}`: {failed_document.error}"
                for failed_document in failed_documents[:3]
            )
            if len(failed_documents) > 3:
                sample += f" (+{len(failed_documents) - 3} more)"
            markdown += (
                f"| `{', '.join(path.name for path in result.feed_paths)}` | "
                f"{result.ok_count}/{result.operation_count} | "
                f"{result.operation_count - result.ok_count} | {sample or '—'} |\n"
            )

    if exceptions:
        markdown += (
            "\n#### Batches that raised\n\n"
            "These never reported a result, so their records were not fed.\n\n"
            "| Exception | Message |\n|---|---|\n"
        )
        for exception in exceptions:
            detail = str(exception).replace("|", "\\|").replace("\n", " ")
            markdown += f"| `{type(exception).__name__}` | {detail} |\n"

    return markdown


def _build_failure_message(
    feed_results: list[FeedResult],
    feed_results_errors: list[FeedResult],
    feed_results_exceptions: list[BaseException],
    records_lost: int,
    run_ui_url: str | None = None,
) -> str:
    """
    The state message for a run that lost records or had a batch raise.

    Prefect shows this verbatim, so it has to say what was lost without a
    traceback to read. Records lost is the figure that matters; batches and
    files locate it.

    `run_ui_url` is `prefect.runtime.flow_run.ui_url`, which is None outside
    a run context.
    """
    total_batches = len(feed_results) + len(feed_results_exceptions)
    parts = []

    if feed_results_errors:
        files_lost = sum(len(result.feed_paths) for result in feed_results_errors)
        parts.append(
            f"lost {records_lost:,} record(s) across "
            f"{len(feed_results_errors)}/{total_batches} batch(es) "
            f"({files_lost} file(s))"
        )

    if feed_results_exceptions:
        # Named rather than counted - which exception it was is the first
        # thing you need, and the state message may be all that is read.
        reasons = ", ".join(
            sorted({type(exception).__name__ for exception in feed_results_exceptions})
        )
        parts.append(
            f"{len(feed_results_exceptions)}/{total_batches} batch(es) "
            f"raised ({reasons})"
        )

    artifact = (
        f"See the run summary artifact at {run_ui_url}/artifacts"
        if run_ui_url
        else "See the vespa-feeder-run-summary artifact"
    )
    return f"vespa_feed: {' and '.join(parts)}. {artifact} for the breakdown."
