from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from vespa_feeder.stream.stream import Stream

logger = logging.getLogger(__name__)


class VespaFeedStats(BaseModel):
    model_config = ConfigDict(frozen=True, validate_by_name=True)
    seconds: float = Field(validation_alias="feeder.seconds")
    ok_count: int = Field(validation_alias="feeder.ok.count")
    error_count: int = Field(validation_alias="feeder.error.count")
    response_error_count: int = Field(validation_alias="http.response.error.count")
    response_code_counts: dict[int, int] = Field(
        validation_alias="http.response.code.counts"
    )
    operation_count: int = Field(validation_alias="feeder.operation.count")

    @classmethod
    def empty(cls) -> VespaFeedStats:
        """Return the stats of a feed that has not done anything yet."""
        return cls(
            seconds=0,
            ok_count=0,
            error_count=0,
            response_error_count=0,
            response_code_counts={},
            operation_count=0,
        )

    @property
    def lost(self) -> int:
        """Records Vespa did not accept."""
        return self.operation_count - self.ok_count

    def since(self, previous: VespaFeedStats) -> VespaFeedStats:
        """Return the change in every count since an earlier snapshot."""

        code_changes = {
            code: count - previous.response_code_counts.get(code, 0)
            for code, count in self.response_code_counts.items()
        }

        return VespaFeedStats(
            seconds=self.seconds - previous.seconds,
            ok_count=self.ok_count - previous.ok_count,
            error_count=self.error_count - previous.error_count,
            response_error_count=self.response_error_count
            - previous.response_error_count,
            response_code_counts=code_changes,
            operation_count=self.operation_count - previous.operation_count,
        )


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
                snapshot = b"".join(snapshot_lines)
                snapshot_lines = []
                yield VespaFeedStats.model_validate_json(snapshot)
        elif line.strip():
            logger.warning(f"vespa feed: {line.decode(errors='replace')}")
