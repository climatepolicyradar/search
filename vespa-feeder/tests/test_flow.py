"""Tests for the Prefect flow."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from vespa_feeder.flow import vespa_feed_flow
from tests.conftest import BUCKET, KEY_PLAIN, KEY_GZ


def test_flow_local(s3_with_feed, feed_job_local, tmp_path):
    """Full flow run against mocked S3, with vespa feed stubbed out."""
    with patch("vespa_feeder.flow.download_feed_file.fn") as mock_dl, \
         patch("vespa_feeder.flow.feed_to_vespa.fn") as mock_feed:

        mock_dl.return_value = tmp_path / "docs.jsonl"
        vespa_feed_flow(feed_job_local)

    mock_dl.assert_called_once()
    mock_feed.assert_called_once()


def test_flow_downloads_and_feeds(s3_with_feed, feed_job_local, tmp_path):
    """Verify download_feed_file calls S3 and feed_to_vespa calls the CLI."""
    downloaded = tmp_path / "docs.jsonl"

    # Patch where the names are used (in the flow module), not where they're defined
    with patch("vespa_feeder.flow.download", return_value=downloaded) as mock_dl, \
         patch("vespa_feeder.flow.feed") as mock_feed:

        downloaded.write_text('{"update": "id:ns:type::1", "fields": {}}\n')
        vespa_feed_flow(feed_job_local)

    mock_dl.assert_called_once()
    mock_feed.assert_called_once_with(
        feed_file=downloaded,
        vespa_url=feed_job_local.vespa_url,
        write_token=None,
    )


def test_flow_passes_write_token(feed_job_cloud, tmp_path):
    """Write token is forwarded to the vespa CLI wrapper."""
    downloaded = tmp_path / "docs.jsonl.gz"

    with patch("vespa_feeder.flow.download", return_value=downloaded), \
         patch("vespa_feeder.flow.feed") as mock_feed:

        downloaded.write_bytes(b"fake")
        vespa_feed_flow(feed_job_cloud)

    mock_feed.assert_called_once_with(
        feed_file=downloaded,
        vespa_url=feed_job_cloud.vespa_url,
        write_token="test-token-abc",
    )
