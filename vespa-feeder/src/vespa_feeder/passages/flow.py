from typing import Any

from prefect.runtime import deployment, flow_run

from prefect import flow
from vespa_feeder.passages.derived_data import (
    is_page_header_or_footer,
    looks_like_demoted_section,
    looks_like_reference_list,
    looks_like_short_heading,
    looks_like_table_of_contents,
)
from vespa_feeder.slack_notify import SlackNotify
from vespa_feeder.stream.metrics import MetricsSink
from vespa_feeder.stream.progress import parse_stats
from vespa_feeder.stream.s3 import S3Source
from vespa_feeder.stream.stream import RUN_TIMEOUT_SECONDS, skip_failures
from vespa_feeder.stream.vespa import VespaFeed, only_if_changed
from vespa_feeder.telemetry import force_flush, shutdown, tracer


def passage_update(row: dict[str, Any]) -> dict[str, Any]:
    """Turn a `fusion.published.vespa_passages` row into a Vespa update."""
    return _derive_passage_type_flags(row["vespa_update"])


def _derive_passage_type_flags(record: dict[str, Any]) -> dict[str, Any]:
    """
    Set the `looks_like_*` bools and `is_page_header_or_footer`.

    Derived from the record's own text, pages and content type. The Fusion
    export doesn't carry them, so without this the fields default
    false and the penalties they drive in passages.sd's `nativerank` profile are
    inert. `pages` is absent for passages with no page data (HTML documents), in
    which case `looks_like_table_of_contents` skips its front-matter page veto.
    """
    fields = record.get("fields", {})
    content = fields.get("content", {}).get("assign", "")
    content_type = fields.get("content_type", {}).get("assign", "")
    heading_text = fields.get("heading_text", {}).get("assign", "")
    pages = fields.get("pages", {}).get("assign") or []
    page_numbers = [page["number"] for page in pages]

    fields["looks_like_short_heading"] = {
        "assign": looks_like_short_heading(content, content_type)
    }
    fields["looks_like_table_of_contents"] = {
        "assign": looks_like_table_of_contents(content, page_numbers)
    }
    fields["looks_like_reference_list"] = {
        "assign": looks_like_reference_list(content, content_type)
    }
    fields["is_page_header_or_footer"] = {
        "assign": is_page_header_or_footer(content_type)
    }
    fields["looks_like_demoted_section"] = {
        "assign": looks_like_demoted_section(heading_text, content, content_type)
    }
    return record


def feed_passages(feed: VespaFeed, metrics: MetricsSink) -> None:
    """Feed the latest passages export into Vespa."""
    source = S3Source(
        bucket="cpr-production-data-lake-fusion",
        prefix="vespa/vespa_passages/",
    )
    updates = source.chain(skip_failures(passage_update)).chain(only_if_changed)
    updates.chain(feed.feed).chain(parse_stats).run(metrics.drain)


@flow(
    name="search-vespa-feeder-passages",
    description="Feed passages JSONL exported from fusion.published.vespa_passages into Vespa",
    timeout_seconds=RUN_TIMEOUT_SECONDS,
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def passages_feeder_flow() -> None:
    try:
        with tracer.start_as_current_span("vespa_feeder"):
            feed = VespaFeed.create_from_ssm()
            metrics = MetricsSink(
                deployment_name=deployment.name or "local",
                run_name=flow_run.name or "unknown",
            )
            feed_passages(feed=feed, metrics=metrics)
    finally:
        force_flush()
        shutdown()
