from __future__ import annotations

import os
import time
from contextlib import suppress
from subprocess import PIPE, CalledProcessError, Popen, TimeoutExpired
from tempfile import NamedTemporaryFile
from typing import IO, Any, cast

import orjson

from vespa_feeder.s3 import get_ssm_parameter
from vespa_feeder.stream.progress import VespaFeedStats
from vespa_feeder.stream.stream import Stream

VESPA_FEED_SETTINGS = [
    # Controls throughput, ~16 matches the old feeders, could maybe push higher
    "--connections",
    "16",
    # Fails if imports keep failing for 10 minutes without a success
    "--deadline",
    "600",
    # Print stats to stderr every 60s, which `progress.parse_stats` picks up
    "--progress",
    "60",
]

# How long `vespa feed` gets to finish in-flight work once its input ends
EXIT_LIMIT_SECONDS = 15 * 60


class VespaFeed:
    def __init__(self, target: str, application: str, token: str) -> None:
        self._target = target
        self._application = application
        self._token = token

    @classmethod
    def create_from_ssm(cls) -> VespaFeed:
        """Create a feed using the Vespa endpoint, application and token from SSM."""
        return cls(
            target=get_ssm_parameter(name="/search/vespa/endpoint"),
            application=get_ssm_parameter(name="/search/vespa/application"),
            token=get_ssm_parameter(name="/search/vespa/write_token"),
        )

    def feed(self, items: Stream[dict[str, Any]]) -> Stream[bytes]:
        """Feed every item to Vespa, yielding what `vespa feed` prints as it runs."""
        with (
            NamedTemporaryFile() as stderr,
            open(stderr.name, "rb") as progress,
            Popen(
                args=self.vespa_feed_args(),
                env={**os.environ, "VESPA_CLI_DATA_PLANE_TOKEN": self._token},
                stderr=stderr,
                stdout=PIPE,
                stdin=PIPE,
            ) as process,
        ):
            try:
                yield from _feed(items=items, process=process, progress=progress)
            except BaseException:
                process.kill()
                _close_stdin(process)
                raise

    def vespa_feed_args(self) -> list[str]:
        """Build the `vespa feed` command line."""
        return [
            "vespa",
            "feed",
            "--application",
            self._application,
            "--target",
            self._target,
            *VESPA_FEED_SETTINGS,
            "-",
        ]


def _feed(
    items: Stream[dict[str, Any]],
    process: Popen[bytes],
    progress: IO[bytes],
) -> Stream[bytes]:
    try:
        yield from _write_items(
            progress=progress,
            process=process,
            items=items,
        )
    except Exception as upstream_error:
        yield from _finish_after_failure(
            upstream_error=upstream_error,
            progress=progress,
            process=process,
        )
        raise
    yield from _finish(
        progress=progress,
        process=process,
    )


def _write_items(
    items: Stream[dict[str, Any]],
    process: Popen[bytes],
    progress: IO[bytes],
) -> Stream[bytes]:
    stdin = cast(IO[bytes], process.stdin)
    for item in items:
        try:
            stdin.write(orjson.dumps(item) + b"\n")
        except BrokenPipeError:
            return
        yield progress.read()


def _finish(process: Popen[bytes], progress: IO[bytes]) -> Stream[bytes]:
    _close_stdin(process)
    yield from _wait_for_exit(
        progress=progress,
        process=process,
    )
    output = cast(IO[bytes], process.stdout).read()
    if process.returncode != 0:
        raise CalledProcessError(
            returncode=process.returncode,
            cmd=process.args,
            output=output,
        )
    VespaFeedStats.model_validate_json(output)
    yield b"\n" + output


def _finish_after_failure(
    process: Popen[bytes],
    progress: IO[bytes],
    upstream_error: Exception,
) -> Stream[bytes]:
    try:
        yield from _finish(
            progress=progress,
            process=process,
        )
    except Exception as finish_error:
        upstream_error.add_note(f"vespa feed then failed: {finish_error!r}")


def _wait_for_exit(process: Popen[bytes], progress: IO[bytes]) -> Stream[bytes]:
    deadline = time.monotonic() + EXIT_LIMIT_SECONDS
    while process.poll() is None:
        if time.monotonic() > deadline:
            raise TimeoutExpired(cmd=process.args, timeout=EXIT_LIMIT_SECONDS)
        with suppress(TimeoutExpired):
            process.wait(timeout=1)
        yield progress.read()
    yield progress.read()


def _close_stdin(process: Popen[bytes]) -> None:
    with suppress(BrokenPipeError):
        cast(IO[bytes], process.stdin).close()
