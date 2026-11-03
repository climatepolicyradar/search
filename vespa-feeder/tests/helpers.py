"""Helpers shared by more than one of the feeder test modules."""

import json
from collections.abc import Callable
from itertools import takewhile
from pathlib import Path

import orjson


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_bytes(b"".join(orjson.dumps(record) + b"\n" for record in records))
    return path


def read_jsonl(path: Path) -> list[dict]:
    return [
        orjson.loads(line) for line in path.read_bytes().splitlines() if line.strip()
    ]


def vespa_feed_stdout(
    operation: int,
    ok: int,
    code_counts: dict[str, int] | None = None,
    feeder_error_count: int = 0,
) -> str:
    """The stats JSON `vespa feed` prints to stdout."""
    code_counts = {"200": ok} if code_counts is None else code_counts
    return json.dumps(
        {
            "feeder.operation.count": operation,
            "feeder.ok.count": ok,
            "feeder.error.count": feeder_error_count,
            "feeder.seconds": 0.5,
            "http.response.error.count": sum(
                count for code, count in code_counts.items() if not code.startswith("2")
            ),
            "http.response.code.counts": code_counts,
        }
    )


def put_s3_objects(s3_client, bucket: str, objects: dict[str, bytes]) -> None:
    """Populate a moto bucket, so the feeder's own `boto3.client` finds the keys."""
    for key, body in objects.items():
        s3_client.put_object(Bucket=bucket, Key=key, Body=body)


class _FakeVespaFeedProcess:
    """The `subprocess.Popen` a `_FakeVespaFeed` hands back."""

    def __init__(self, feed: "_FakeVespaFeed", argv: list[str], stdout: str) -> None:
        self.args = argv
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._feed = feed
        self._stdout = stdout

    def communicate(self, timeout: int | None = None) -> tuple[str, str]:
        self._feed.timeouts.append(timeout)
        if self._feed.on_communicate is not None:
            self._feed.on_communicate(self)
        self.returncode = self._feed.returncode
        return self._stdout, self._feed.stderr

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def __enter__(self) -> "_FakeVespaFeedProcess":
        return self

    def __exit__(self, *_) -> bool:
        return False


class _FakeVespaFeed:
    """
    Stands in for `subprocess.Popen`, recording what `vespa feed` was handed.

    It reads the feed files off disk when the process is spawned, so
    `fed_records` is proof the files still existed and held records at the
    moment they were fed.

    `on_communicate` runs while the process is live and registered in
    `_vespa_feed_processes` - the only window in which a SIGTERM has anything
    to terminate.
    """

    def __init__(
        self,
        stdout: str | None = None,
        stderr: str = "",
        returncode: int = 0,
        on_communicate: Callable[[_FakeVespaFeedProcess], None] | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.on_communicate = on_communicate
        self.calls: list[list[str]] = []
        self.timeouts: list[int | None] = []
        self.fed_records: list[dict] = []
        self.processes: list[_FakeVespaFeedProcess] = []

    def __call__(self, argv: list[str], **kwargs) -> _FakeVespaFeedProcess:
        self.calls.append(argv)

        feed_paths = takewhile(lambda arg: not arg.startswith("--"), argv[2:])
        records = [record for path in feed_paths for record in read_jsonl(Path(path))]
        self.fed_records.extend(records)

        stdout = self.stdout or vespa_feed_stdout(
            operation=len(records), ok=len(records)
        )
        process = _FakeVespaFeedProcess(self, argv, stdout)
        self.processes.append(process)
        return process
