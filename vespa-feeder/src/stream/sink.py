from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import AbstractContextManager, closing, contextmanager, suppress
from subprocess import PIPE, CalledProcessError, Popen
from typing import IO, Any, cast

import orjson
from pydantic import BaseModel, ConfigDict, Field
from s3 import get_ssm_parameter
from telemetry import feeder_metrics, set_feed_stats

# connections: Controls throughput, ~16 matches the old feeders, could maybe push higher
# deadline: Fails if imports keep failing for 10 minutes without a success
# progress: Logs stats out to stderr for debugging

VESPA_FEED_SETTINGS = [
    "--connections",
    "16",
    "--deadline",
    "600",
    "--progress",
    "60",
]


class RecordsLost(Exception):
    def __init__(self, summary: VespaFeedSummary) -> None:
        super().__init__(f"{summary.lost} of {summary.operation_count} records lost")


class VespaStoppedReading(Exception):
    pass


class Sink[A](ABC):
    @abstractmethod
    def write(self, line: A) -> None:
        """Write one item to the sink."""
        ...


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


class VespaSink(Sink[dict[str, Any]]):
    def __init__(self, stdin: IO[bytes]) -> None:
        self._stdin = stdin

    def write(self, line: dict[str, Any]) -> None:
        """Send one document to `vespa feed`."""
        try:
            self._stdin.write(orjson.dumps(line) + b"\n")
        except BrokenPipeError as error:
            raise VespaStoppedReading from error

    def close(self) -> None:
        """Close stdin so `vespa feed` sees the end of its input."""
        with suppress(BrokenPipeError):
            self._stdin.close()

    def _log_results(self, results: bytes, deployment_name: str, run_name: str) -> None:
        summary = VespaFeedSummary.model_validate_json(results)
        throttled = summary.response_code_counts.get(429, 0)

        feeder_metrics.record_feed_stats(
            total_errors=summary.lost,
            deployment_name=deployment_name,
            input_count=summary.operation_count,
            ok_count=summary.ok_count,
            run_name=run_name,
        )

        feeder_metrics.record_retry_stats(
            other_http_error_count=summary.response_error_count - throttled,
            feeder_error_count=summary.error_count,
            deployment_name=deployment_name,
            throttled_count=throttled,
            run_name=run_name,
            file_count=0,
        )

        feeder_metrics.record_run_duration(
            deployment_name=deployment_name,
            duration_s=summary.seconds,
            run_name=run_name,
        )

        set_feed_stats(
            total_errors=summary.lost,
            input_count=summary.operation_count,
            ok_count=summary.ok_count,
        )

        if summary.lost > 0:
            raise RecordsLost(summary)

    @staticmethod
    @contextmanager
    def _feeding(process: Popen[bytes]) -> Generator[None]:
        try:
            yield
        except VespaStoppedReading:
            pass
        except BaseException:
            process.kill()
            raise

    @classmethod
    def create_from_ssm(
        cls,
        deployment_name: str,
        run_name: str,
    ) -> AbstractContextManager[VespaSink]:
        """Create a sink using the Vespa endpoint, application and token from SSM."""
        return cls.create(
            target=get_ssm_parameter(name="/search/vespa/endpoint"),
            application=get_ssm_parameter(name="/search/vespa/application"),
            token=get_ssm_parameter(name="/search/vespa/write_token"),
            deployment_name=deployment_name,
            run_name=run_name,
        )

    @staticmethod
    def _vespa_feed_args(target: str, application: str) -> list[str]:
        return [
            "vespa",
            "feed",
            "--application",
            application,
            "--target",
            target,
            *VESPA_FEED_SETTINGS,
            "-",
        ]

    @classmethod
    @contextmanager
    def create(
        cls,
        target: str,
        application: str,
        token: str,
        deployment_name: str,
        run_name: str,
    ) -> Generator[VespaSink]:
        """Run `vespa feed` for the duration of the block, raising if it fails."""
        with Popen(
            args=cls._vespa_feed_args(target=target, application=application),
            env={**os.environ, "VESPA_CLI_DATA_PLANE_TOKEN": token},
            stdout=PIPE,
            stdin=PIPE,
        ) as process:
            stdin = cast(IO[bytes], process.stdin)
            stdout = cast(IO[bytes], process.stdout)
            try:
                with closing(sink := cls(stdin=stdin)), sink._feeding(process):
                    yield sink

                output = stdout.read()
                if process.wait() != 0:
                    raise CalledProcessError(
                        returncode=process.returncode,
                        cmd=process.args,
                        output=output,
                    )

                sink._log_results(
                    deployment_name=deployment_name,
                    run_name=run_name,
                    results=output,
                )
            except Exception:
                feeder_metrics.record_run_failed(
                    deployment_name=deployment_name,
                    run_name=run_name,
                )
                raise

            feeder_metrics.record_run_completed(
                deployment_name=deployment_name,
                run_name=run_name,
            )
