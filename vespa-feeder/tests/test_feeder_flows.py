"""
Tests for the three wrapper flows Prefect actually deploys.

Each flow is a thin shim that calls `vespa_feeder` with its own bucket, prefix
and deriver, so the realistic failure is a copy-paste slip between the three
near-identical wrappers - a flow pointed at the wrong prefix, or running
another flow's deriver. These run the real flows under `prefect_test_harness`
with `vespa_feeder` replaced, and assert on the arguments it received.
"""

import pytest
from vespa_feeder import documents_flow, labels_flow, passages_flow
from vespa_feeder.slack_notify import SlackNotify

SNOWFLAKE_EXPORT_BUCKET = "cpr-prod-snowflake-data-export"


@pytest.fixture
def recorded_feeder_calls(monkeypatch):
    """
    Replace `vespa_feeder` in all three flow modules with a recorder.

    Each module does `from vespa_feeder import vespa_feeder`, so the name has to
    be patched per importing module, not on the source module. Returns the list
    the recorder appends each call's kwargs to.
    """
    calls: list[dict] = []

    def recorder(**kwargs) -> None:
        calls.append(kwargs)

    for module in (passages_flow, documents_flow, labels_flow):
        monkeypatch.setattr(module, "vespa_feeder", recorder)
    return calls


def test_passages_flow_feeds_the_passages_export_with_the_passages_deriver(
    prefect_db, recorded_feeder_calls
) -> None:
    passages_flow.passages_feeder_flow()

    (call,) = recorded_feeder_calls
    assert call["s3_bucket"] == SNOWFLAKE_EXPORT_BUCKET
    assert (
        call["s3_prefix"]
        == "production/published/pipeline_data_in_vespa_passage_updates_v1/"
    )
    assert call["derive_data_from_source"] is passages_flow.derive_passage_data


def test_labels_flow_feeds_the_fusion_export_with_no_deriver(
    prefect_db, recorded_feeder_calls
) -> None:
    """
    Labels from Fusion feed the dated `vespa_labels` export folder as-is.

    Each Fusion row is already a Vespa update operation, so no deriver is
    passed. A folder prefix (not a `.jsonl` key) makes `vespa_feeder` pick the
    newest timestamped snapshot, and `s3_export_prefix` is passed through so a
    run can be pinned to one.
    """
    labels_flow.labels_feeder_flow()

    (call,) = recorded_feeder_calls
    assert call["s3_bucket"] == "cpr-production-data-lake-fusion"
    assert call["s3_prefix"] == "vespa/vespa_labels/"
    assert call["s3_export_prefix"] is None
    assert "derive_data_from_source" not in call


def test_documents_flow_feeds_the_fusion_export_with_the_fusion_deriver(
    prefect_db, recorded_feeder_calls
) -> None:
    """
    Documents from Fusion feed the dated `vespa_documents` export folder.

    Fusion rows are flat objects keyed by field name, not Vespa updates, so the
    flow passes the deriver that wraps each one in an update operation.
    """
    documents_flow.documents_feeder_flow()

    (call,) = recorded_feeder_calls
    assert call["s3_bucket"] == "cpr-production-data-lake-fusion"
    assert call["s3_prefix"] == "vespa/vespa_documents/"
    assert call["s3_export_prefix"] is None
    assert call["derive_data_from_source"] is documents_flow.derive_fusion_document_data


def test_documents_flow_passes_a_pinned_export_prefix_through(
    prefect_db, recorded_feeder_calls
) -> None:
    documents_flow.documents_feeder_flow(s3_export_prefix="20261119T100000Z")

    (call,) = recorded_feeder_calls
    assert call["s3_export_prefix"] == "20261119T100000Z"


def test_labels_flow_passes_a_pinned_export_prefix_through(
    prefect_db, recorded_feeder_calls
) -> None:
    labels_flow.labels_feeder_flow(s3_export_prefix="20261119T100000Z")

    (call,) = recorded_feeder_calls
    assert call["s3_export_prefix"] == "20261119T100000Z"


# `_max_workers` is private, but `ThreadPoolTaskRunner` exposes the cap nowhere
# else, and the cap is the whole reason `task_runner()` exists - see its
# docstring and the submit loop in `vespa_feeder`. Reading the private attribute
# is worth it to catch a wrapper being given the wrong one.
@pytest.mark.parametrize(
    ("flow", "expected_max_workers"),
    [
        (passages_flow.passages_feeder_flow, 8),
        (documents_flow.documents_feeder_flow, 4),
        (labels_flow.labels_feeder_flow, 4),
    ],
)
def test_flow_bounds_its_task_runner(flow, expected_max_workers: int) -> None:
    assert flow.task_runner._max_workers == expected_max_workers


@pytest.mark.parametrize(
    "flow",
    [
        passages_flow.passages_feeder_flow,
        documents_flow.documents_feeder_flow,
        labels_flow.labels_feeder_flow,
    ],
)
def test_flow_notifies_slack_on_every_terminal_state(flow) -> None:
    """All four terminal states notify Slack, so a failure is never silent."""
    hooks = {
        "on_completion": flow.on_completion_hooks,
        "on_failure": flow.on_failure_hooks,
        "on_crashed": flow.on_crashed_hooks,
        "on_cancellation": flow.on_cancellation_hooks,
    }
    for name, registered in hooks.items():
        assert registered, f"{name} has no hook registered"
        assert all(hook.__self__ is SlackNotify for hook in registered), (
            f"{name} is not handled by SlackNotify"
        )
