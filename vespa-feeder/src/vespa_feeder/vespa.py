"""
Thin wrapper around the `vespa feed` CLI command.

Mirrors the pattern used in vespa/justfile:

  vespa feed <file> --target $vespa_endpoint \
      --header "Authorization: Bearer $vespa_write_token" \
      --progress 30
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def feed(
    feed_file: Path,
    vespa_url: str,
    write_token: str | None = None,
    progress: int = 30,
) -> None:
    """
    Run ``vespa feed`` against the given file.

    Parameters
    ----------
    feed_file:
        Local path to a JSONL or JSONL.gz feed file.
    vespa_url:
        Target Vespa endpoint, e.g. ``http://localhost:8080`` or
        ``https://my-app.vespa-cloud.com``.
    write_token:
        Bearer token for Vespa Cloud.  Omit for local / unauthenticated use.
    progress:
        How often (in seconds) the vespa CLI prints progress.

    Raises
    ------
    subprocess.CalledProcessError
        If the ``vespa feed`` command exits with a non-zero status.
    """
    cmd = [
        "vespa", "feed", str(feed_file),
        "--target", vespa_url,
        "--progress", str(progress),
    ]

    if write_token:
        cmd += ["--header", f"Authorization: Bearer {write_token}"]

    subprocess.run(cmd, check=True)
