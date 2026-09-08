import json

from flow import vespa_feeder
from prefect.client.schemas.objects import State
from slack_notify import SlackNotify

from prefect import flow


def derive_label_source(record: dict) -> dict:
    """
    Set `label_source` on a labels update record, derived from its own id/type/value/labels.

    `label_source` must deserialize as `search.data_in_models.Label` (a flat
    id/type/value/labels envelope) - the labels search engine parses it via
    `DataInLabel.model_validate_json` at query time, and silently drops the
    label if it's missing/unparseable. It is not produced by dbt (there's
    nothing in it that isn't already derivable from this same record's other
    fields), so it's reconstructed here instead, the same way documents_flow.py
    derives `principal_id` and passages_flow.py derives `labels`/`document_ref`.
    """
    fields = record.get("fields", {})
    label_id = fields.get("id", {}).get("assign")
    label_type = fields.get("type", {}).get("assign")
    value = fields.get("value", {}).get("assign")
    relationships = fields.get("labels", {}).get("assign", [])

    relationship_entries = []
    for rel in relationships:
        try:
            relationship_entries.append(
                {
                    "type": rel["relationship"],
                    "value": {
                        "id": rel["id"],
                        "type": rel["type"],
                        "value": rel["value"],
                        "labels": [],
                    },
                    "timestamp": None,
                }
            )
        except KeyError as e:
            print(
                f"WARNING: skipping malformed label relationship on {label_id!r} "
                f"(missing key {e}): {rel!r}"
            )

    label_source = {
        "id": label_id,
        "type": label_type,
        "value": value,
        "labels": relationship_entries,
    }

    record["fields"]["label_source"] = {"assign": json.dumps(label_source)}
    return record


def derive_label_data(record: dict) -> dict:
    """Apply all labels derivers to a record, in sequence."""
    return derive_label_source(record)


@flow(
    name="search-vespa-feeder-labels",
    description="Feed labels JSONL from the data-lake Snowflake export into Vespa, deriving label_source per record",
    log_prints=True,
    on_completion=[SlackNotify.on_success],
    on_failure=[SlackNotify.on_failure],
    on_crashed=[SlackNotify.on_crashed],
    on_cancellation=[SlackNotify.on_cancellation],
)
def labels_feeder_flow() -> State | None:
    # Data-lake export files are ~100x smaller than the old materializer's -
    # see flow.py's _DEFAULT_MAX_CONCURRENT_DOWNLOADS for why 8 is safe here.
    return vespa_feeder(
        s3_bucket="cpr-prod-snowflake-data-export",
        s3_key="production/published/pipeline_data_in_vespa_label_updates_v1/latest",
        derive_data_from_source=derive_label_data,
        max_concurrent_downloads=8,
    )
