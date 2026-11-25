from __future__ import annotations

import os
from contextlib import suppress
from subprocess import PIPE, CalledProcessError, Popen
from typing import IO, Any, cast

import orjson
from pydantic import BaseModel, ConfigDict, Field

from vespa_feeder.s3 import get_ssm_parameter
from vespa_feeder.stream.stream import Stream
from vespa_feeder.telemetry import feeder_metrics, set_feed_stats

VESPA_FEED_SETTINGS = [
    # Controls throughput, ~16 matches the old feeders, could maybe push higher
    "--connections",
    "16",
    # Fails if imports keep failing for 10 minutes without a success
    "--deadline",
    "600",
    # Log stats out to stderr every 60s for debugging
    "--progress",
    "60",
]


class RecordsLost(Exception):
    def __init__(self, summary: VespaFeedSummary) -> None:
        super().__init__(f"{summary.lost} of {summary.operation_count} records lost")


class VespaFeedSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    seconds: float = Field(alias="feeder.seconds")
    ok_count: int = Field(alias="feeder.ok.count")
    error_count: int = Field(alias="feeder.error.count")
    response_error_count: int = Field(alias="http.response.error.count")
    response_code_counts: dict[int, int] = Field(alias="http.response.code.counts")
    operation_count: int = Field(alias="feeder.operation.count")

    @property
    def lost(self) -> int:
        """Records Vespa did not accept."""
        return self.operation_count - self.ok_count


class VespaSink:
    def __init__(
        self,
        target: str,
        application: str,
        token: str,
        deployment_name: str,
        run_name: str,
    ) -> None:
        self._target = target
        self._application = application
        self._token = token
        self._deployment_name = deployment_name
        self._run_name = run_name

    @classmethod
    def create_from_ssm(cls, deployment_name: str, run_name: str) -> VespaSink:
        """Create a sink using the Vespa endpoint, application and token from SSM."""
        return cls(
            target=get_ssm_parameter(name="/search/vespa/endpoint"),
            application=get_ssm_parameter(name="/search/vespa/application"),
            token=get_ssm_parameter(name="/search/vespa/write_token"),
            deployment_name=deployment_name,
            run_name=run_name,
        )

    def drain(self, items: Stream[dict[str, Any]]) -> None:
        """Feed every item to Vespa through one `vespa feed` process."""
        with Popen(
            args=self.vespa_feed_args(),
            env={**os.environ, "VESPA_CLI_DATA_PLANE_TOKEN": self._token},
            stdout=PIPE,
            stdin=PIPE,
        ) as process:
            try:
                self._write(items=items, process=process)
            except BaseException:
                process.kill()
                with suppress(BrokenPipeError):
                    cast(IO[bytes], process.stdin).close()
                feeder_metrics.record_run_failed(
                    deployment_name=self._deployment_name,
                    run_name=self._run_name,
                )
                raise

            feeder_metrics.record_run_completed(
                deployment_name=self._deployment_name,
                run_name=self._run_name,
            )

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

    def _write(self, items: Stream[dict[str, Any]], process: Popen[bytes]) -> None:
        stdin = cast(IO[bytes], process.stdin)
        try:
            for item in items:
                try:
                    stdin.write(orjson.dumps(item) + b"\n")
                except BrokenPipeError:
                    break
        except Exception as upstream_error:
            try:
                self._finish(process=process)
            except Exception as finish_error:
                upstream_error.add_note(f"vespa feed then failed: {finish_error!r}")
            raise
        self._finish(process=process)

    def _finish(self, process: Popen[bytes]) -> None:
        output = process.communicate(timeout=15 * 60)[0]
        if process.returncode != 0:
            raise CalledProcessError(
                returncode=process.returncode,
                cmd=process.args,
                output=output,
            )

        summary = VespaFeedSummary.model_validate_json(output)
        throttled = summary.response_code_counts.get(429, 0)

        feeder_metrics.record_feed_stats(
            total_errors=summary.lost,
            deployment_name=self._deployment_name,
            input_count=summary.operation_count,
            ok_count=summary.ok_count,
            run_name=self._run_name,
        )

        feeder_metrics.record_retry_stats(
            other_http_error_count=summary.response_error_count - throttled,
            feeder_error_count=summary.error_count,
            deployment_name=self._deployment_name,
            throttled_count=throttled,
            run_name=self._run_name,
            file_count=0,
        )

        feeder_metrics.record_run_duration(
            deployment_name=self._deployment_name,
            duration_s=summary.seconds,
            run_name=self._run_name,
        )

        set_feed_stats(
            total_errors=summary.lost,
            input_count=summary.operation_count,
            ok_count=summary.ok_count,
        )

        if summary.lost > 0:
            raise RecordsLost(summary)
