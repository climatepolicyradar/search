from collections.abc import Generator
from contextlib import contextmanager

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from pydantic_evals.reporting import EvaluationReport

from relevance.reporters import common


@contextmanager
def init(dataset_name: str) -> Generator[Meter]:
    resource = Resource.create(
        {
            "service.name": "relevance",
            "dataset.name": dataset_name,
            "branch": common.branch(),
        }
    )

    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider([reader], resource=resource)

    try:
        yield provider.get_meter("relevance")
    finally:
        provider.shutdown()


def report[I, O](
    meter: Meter,
    dataset_name: str,
    report: EvaluationReport[I, O, dict[str, str]],
) -> None:
    score_histogram = meter.create_histogram(
        description="Per-suite average evaluator scores",
        name="relevance_score",
        unit="1",
    )

    if averages := report.averages():
        for name, value in averages.scores.items():
            score_histogram.record(
                attributes={"suite": dataset_name, "metric": name},
                amount=value,
            )

        if averages.assertions:
            score_histogram.record(
                attributes={"suite": dataset_name, "metric": "pass_rate"},
                amount=averages.assertions,
            )

    error_counter = meter.create_counter(
        description="Evaluator cases that errored",
        name="relevance_errors",
        unit="1",
    )

    error_counter.add(
        attributes={"suite": dataset_name},
        amount=len(report.failures), 
    )
