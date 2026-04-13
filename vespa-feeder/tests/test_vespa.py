"""Tests for the vespa CLI wrapper."""

import subprocess
from pathlib import Path
from unittest.mock import patch, call

import pytest

from vespa_feeder.vespa import feed


@pytest.fixture
def feed_file(tmp_path) -> Path:
    f = tmp_path / "docs.jsonl"
    f.write_text('{"update": "id:ns:type::1", "fields": {}}\n')
    return f


def test_feed_local_no_token(feed_file):
    with patch("subprocess.run") as mock_run:
        feed(feed_file, "http://localhost:8080")

    mock_run.assert_called_once_with(
        ["vespa", "feed", str(feed_file), "--target", "http://localhost:8080", "--progress", "30"],
        check=True,
    )


def test_feed_cloud_with_token(feed_file):
    with patch("subprocess.run") as mock_run:
        feed(feed_file, "https://my-app.vespa-cloud.com", write_token="tok-abc")

    mock_run.assert_called_once_with(
        [
            "vespa", "feed", str(feed_file),
            "--target", "https://my-app.vespa-cloud.com",
            "--progress", "30",
            "--header", "Authorization: Bearer tok-abc",
        ],
        check=True,
    )


def test_feed_custom_progress(feed_file):
    with patch("subprocess.run") as mock_run:
        feed(feed_file, "http://localhost:8080", progress=60)

    args = mock_run.call_args[0][0]
    assert "--progress" in args
    assert args[args.index("--progress") + 1] == "60"


def test_feed_propagates_subprocess_error(feed_file):
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "vespa")):
        with pytest.raises(subprocess.CalledProcessError):
            feed(feed_file, "http://localhost:8080")
