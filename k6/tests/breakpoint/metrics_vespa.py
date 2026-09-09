"""
Poll Vespa container-node metrics during a load test, to JSONL.

Why this exists rather than reading the `vespa` CloudWatch namespace: that is
emitted on `rate(5 minutes)` by the navigator-infra metrics Lambda, which is
too coarse to attribute anything to a 5-minute load step. This polls the data
plane directly, so we get ~30 samples per step instead of one.

What it can and cannot see -- verified against production, not assumed:

- `/state/v1/metrics` (used here) returns ~229 metrics from a **container**
  node: `jdisc.thread_pool.*`, `query_latency`, `serverNumRequests`,
  `serverNumOpenConnections`, `mem.*`, `jvm.*`. That covers the query front
  door, which on a 2-vCPU x 2-node container cluster is where we expect
  saturation to show first.
- It does **not** return `content.proton.*` -- those live on the content nodes,
  which the data plane will not route to. Content-node CPU, memory and disk
  have to come from the 5-minute CloudWatch data (see metrics_aws.py).
- The endpoint is load-balanced across both container nodes, so each poll is a
  sample from *one* of them, chosen by the LB. Treat thread-pool numbers as a
  sampled distribution across the cluster, not a single node's timeline.
- `/metrics/v2/values` looks like the right endpoint but returns node roles
  with empty `services` arrays -- no values. It is used here only to record
  the topology once, for the run log.

Usage:
    python metrics_vespa.py --once                 # verify access, print, exit
    python metrics_vespa.py --out results/vespa.jsonl --interval 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any, Final

import requests

logging.basicConfig(
    format="%(asctime)s\t%(levelname)s\t%(message)s", level=logging.INFO
)
logger = logging.getLogger("metrics_vespa")

REQUEST_TIMEOUT_S: Final = 20

# Give up if the endpoint fails this many times in a row. A single failed poll
# is per-sample degradation and gets recorded in-band (see poll_loop); a
# sustained outage means the run's data is worthless and we should say so
# loudly rather than write a file full of error records.
MAX_CONSECUTIVE_FAILURES: Final = 6

# Explicit allowlist, in the spirit of the CloudWatch emitter's. Prefix match,
# so `jdisc.thread_pool` picks up `.size`, `.active_threads`,
# `.work_queue.size`, `.rejected_tasks` and friends without having to enumerate
# them -- `rejected_tasks` in particular only appears once it is non-zero.
METRIC_PREFIXES: Final = (
    "jdisc.thread_pool",
    "query_latency",
    "mean_query_latency",
    "max_query_latency",
    "serverNumRequests",
    "serverNumSuccessfulResponses",
    "serverNumConnections",
    "serverNumOpenConnections",
    "mem.heap",
    "mem.native",
    "jvm.memory",
    "feed.latency",
    "feed.operations",
)


class VespaMetricsError(RuntimeError):
    """
    A metrics scrape failed. Raised rather than returning a partial dict.

    An empty or partial sample is indistinguishable from a genuinely idle
    Vespa, which is exactly the confusion docs/errors.md is about: a run where
    the API is on fire and one where nobody is querying would look the same.
    """


def _settings() -> tuple[str, str]:
    """
    Resolve the Vespa endpoint and read token, or raise.

    Reads the same env vars the API uses (VESPA_ENDPOINT / VESPA_READ_TOKEN),
    which `just` loads from the repo-root .env via `set dotenv-load`.
    """
    endpoint = os.environ.get("VESPA_ENDPOINT", "").rstrip("/")
    token = os.environ.get("VESPA_READ_TOKEN", "")
    if not endpoint or not token:
        raise VespaMetricsError(
            "VESPA_ENDPOINT and VESPA_READ_TOKEN must both be set. "
            "They are in the repo-root .env; `just` loads it automatically, "
            "or run: set -a && . ./.env && set +a"
        )
    return endpoint, token


def fetch_topology(
    session: requests.Session, endpoint: str, token: str
) -> list[dict[str, str]]:
    """Record which nodes exist, once, for the run log."""
    response = session.get(
        f"{endpoint}/metrics/v2/values",
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT_S,
    )
    if not response.ok:
        raise VespaMetricsError(
            f"topology scrape failed: HTTP {response.status_code} {response.text[:200]}"
        )
    return [
        {"hostname": node["hostname"], "role": node["role"]}
        for node in response.json()["nodes"]
    ]


def poll_once(session: requests.Session, endpoint: str, token: str) -> dict[str, Any]:
    """Scrape one sample. Raises VespaMetricsError; never returns a partial."""
    url = f"{endpoint}/state/v1/metrics"
    try:
        response = session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise VespaMetricsError(f"transport error scraping {url}: {exc}") from exc

    if not response.ok:
        raise VespaMetricsError(
            f"HTTP {response.status_code} scraping {url}: {response.text[:200]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise VespaMetricsError(f"non-JSON body from {url}: {exc}") from exc

    values = payload.get("metrics", {}).get("values")
    if values is None:
        raise VespaMetricsError(
            f"no metrics.values in payload from {url}; keys were {sorted(payload)}"
        )

    sample: dict[str, Any] = {
        "ts": time.time(),
        "ok": True,
        "status": payload.get("status", {}).get("code"),
        "vespa_time": payload.get("time"),
        "metrics": [],
    }
    for entry in values:
        name = entry.get("name", "")
        if not name.startswith(METRIC_PREFIXES):
            continue
        sample["metrics"].append(
            {
                "name": name,
                "values": entry.get("values", {}),
                "dimensions": entry.get("dimensions", {}),
            }
        )
    return sample


def poll_loop(
    session: requests.Session,
    endpoint: str,
    token: str,
    out_path: pathlib.Path,
    interval_s: float,
    duration_s: float | None,
) -> None:
    started = time.monotonic()
    consecutive_failures = 0
    written = 0

    with out_path.open("a", encoding="utf-8") as handle:
        while duration_s is None or (time.monotonic() - started) < duration_s:
            try:
                sample = poll_once(session, endpoint, token)
                consecutive_failures = 0
            except VespaMetricsError as exc:
                # Per-item degradation, per docs/errors.md: one bad sample must
                # not end a 35-minute run. But it is written as an explicit
                # error record so the gap is visible in the data rather than
                # looking like a quiet period.
                consecutive_failures += 1
                logger.warning(
                    f"poll failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {exc}"
                )
                sample = {"ts": time.time(), "ok": False, "error": str(exc)}
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    handle.write(json.dumps(sample) + "\n")
                    handle.flush()
                    raise VespaMetricsError(
                        f"{consecutive_failures} consecutive scrape failures; "
                        f"the run's Vespa data is not trustworthy. Last error: {exc}"
                    ) from exc

            handle.write(json.dumps(sample) + "\n")
            handle.flush()  # so the file is readable mid-run
            written += 1
            if written % 30 == 0:
                logger.info(f"{written} samples -> {out_path}")
            time.sleep(interval_s)

    logger.info(f"Done: {written} samples -> {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="take a single sample, print it, and exit (access check)",
    )
    parser.add_argument("--out", default="results/vespa.jsonl")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="seconds to poll for; omit to run until interrupted",
    )
    args = parser.parse_args()

    endpoint, token = _settings()
    session = requests.Session()

    if args.once:
        topology = fetch_topology(session, endpoint, token)
        for node in topology:
            logger.info(f"node {node['role']}\t{node['hostname']}")
        sample = poll_once(session, endpoint, token)
        print(json.dumps(sample, indent=2))
        logger.info(f"OK: {len(sample['metrics'])} metrics matched the allowlist")
        return 0

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Fail fast on misconfiguration: if the very first scrape does not work,
    # there is no point starting a 35-minute run that will produce nothing.
    poll_once(session, endpoint, token)
    topology = fetch_topology(session, endpoint, token)
    logger.info(
        f"Polling every {args.interval}s -> {out_path} "
        f"({len(topology)} nodes; container-node metrics only)"
    )

    try:
        poll_loop(session, endpoint, token, out_path, args.interval, args.duration)
    except KeyboardInterrupt:
        logger.info("Interrupted; samples already written are intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
