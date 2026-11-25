from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from vespa_feeder.stream.stream import Stream, run_logger


class IncompleteStats(Exception):
    def __init__(self) -> None:
        super().__init__("vespa feed output ended part-way through its stats")


class VespaFeedStats(BaseModel):
    model_config = ConfigDict(frozen=True, validate_by_name=True)
    seconds: float = Field(validation_alias="feeder.seconds")
    ok_count: int = Field(validation_alias="feeder.ok.count")
    ok_rate: float = Field(validation_alias="feeder.ok.rate")
    error_count: int = Field(validation_alias="feeder.error.count")
    response_error_count: int = Field(validation_alias="http.response.error.count")
    response_codes: dict[int, int] = Field(validation_alias="http.response.code.counts")
    operation_count: int = Field(validation_alias="feeder.operation.count")

    @classmethod
    def empty(cls) -> VespaFeedStats:
        """Return the stats of a feed that has not done anything yet."""
        return cls(
            seconds=0,
            ok_count=0,
            ok_rate=0,
            error_count=0,
            response_error_count=0,
            response_codes={},
            operation_count=0,
        )

    def since(self, previous: VespaFeedStats) -> VespaFeedStats:
        """Return the change in every count since an earlier snapshot."""

        code_changes = {
            code: count - previous.response_codes.get(code, 0)
            for code, count in self.response_codes.items()
        }

        return VespaFeedStats(
            ok_rate=self.ok_rate,
            seconds=self.seconds - previous.seconds,
            ok_count=self.ok_count - previous.ok_count,
            error_count=self.error_count - previous.error_count,
            response_error_count=self.response_error_count - previous.response_error_count,
            operation_count=self.operation_count - previous.operation_count,
            response_codes=code_changes,
        )

    def describe(self) -> str:
        """Return a one-line summary for the logs."""
        return f"{self.operation_count} fed, {self.ok_rate:.0f} ok/s, {self.error_count} errors"


def _lines(output: Stream[bytes]) -> Stream[bytes]:
    partial_line = b""
    for chunk in output:
        lines = (partial_line + chunk).split(b"\n")
        partial_line = lines.pop()
        yield from lines
    yield partial_line


def parse_stats(output: Stream[bytes]) -> Stream[VespaFeedStats]:
    """Yield each stats snapshot in `vespa feed` output, logging the other lines."""
    snapshot_lines: list[bytes] = []
    for line in _lines(output):
        if line == b"{" or snapshot_lines:
            snapshot_lines.append(line)
            if line == b"}":
                stats = VespaFeedStats.model_validate_json(b"".join(snapshot_lines))
                run_logger().info(f"vespa feed: {stats.describe()}")
                snapshot_lines = []
                yield stats
        elif line.strip():
            run_logger().warning(f"vespa feed: {line.decode(errors='replace')}")

    if snapshot_lines:
        raise IncompleteStats
