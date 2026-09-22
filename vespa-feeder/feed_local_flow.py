"""
Run the real passages flow locally against an ephemeral Prefect backend.

`prefect_test_harness` stands up a temporary SQLite database and a local API
server, and repoints `PREFECT_API_URL` at it. That means the flow runs its
actual code - `vespa_feeder`, `download_and_feed`, `derive_passage_data`, the
`vespa feed` subprocess - with no connection to Prefect Cloud, and therefore
no events websocket. The Cloud websocket is what drops mid-run and wedges the
nightly deployment, so this path should not hit that failure.

Note what this is and is not:

- It IS the production code path, so anything that breaks in the feed logic
  itself will break here too.
- It is NOT a reproduction of the wedge. There is no Cloud connection to lose,
  so a clean run here says nothing about whether the deployment is fixed.

The only deliberate differences from `passages_feeder_flow` are `max_files`
(so you can trial a handful before committing to ~5.9k) and the absence of the
Slack state hooks, which load a Prefect Block that does not exist in the
throwaway database.

Usage (needs AWS credentials for the SSM reads and the S3 listing):

    AWS_PROFILE=production uv run python vespa-feeder/feed_local_flow.py --max-files 20
    AWS_PROFILE=production uv run python vespa-feeder/feed_local_flow.py
"""

from __future__ import annotations

import argparse
import sys

from flow import feed_task_runner, vespa_feeder
from passages_flow import derive_passage_data
from prefect.client.schemas.objects import State
from prefect.testing.utilities import prefect_test_harness

from prefect import flow

S3_BUCKET = "cpr-prod-snowflake-data-export"
S3_ROOT = "production/published/pipeline_data_in_vespa_passage_updates_v1"


def build_flow(max_files: int | None, workers: int):
    """
    Mirror of `passages_feeder_flow` with `max_files` threaded through.

    Built here rather than imported because the deployed flow takes no
    arguments, and trialling a subset is the whole point of running locally.
    """

    @flow(
        name="search-vespa-feeder-passages-local",
        task_runner=feed_task_runner(max_workers=workers),
        log_prints=True,
    )
    def passages_feeder_flow_local(prefix: str) -> State | None:
        return vespa_feeder(
            s3_bucket=S3_BUCKET,
            s3_key=f"{S3_ROOT}/{prefix.strip('/')}",
            derive_data_from_source=derive_passage_data,
            max_files=max_files,
        )

    return passages_feeder_flow_local


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        default="latest",
        help=(
            "Snapshot to feed. 'latest' is rewritten in place by the Snowflake "
            "export over ~27 minutes; pass a timestamped snapshot "
            "(e.g. 20260917T083543Z) for a stable read."
        ),
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Feed only the first N files. Omit to feed the whole snapshot.",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--server-startup-timeout",
        type=int,
        default=60,
        help="Seconds to wait for the ephemeral API server (default 30 is tight).",
    )
    config = parser.parse_args()

    print(
        f"running passages feed locally: prefix={config.prefix} "
        f"max_files={config.max_files} workers={config.workers}",
        flush=True,
    )
    with prefect_test_harness(server_startup_timeout=config.server_startup_timeout):
        build_flow(config.max_files, config.workers)(prefix=config.prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
