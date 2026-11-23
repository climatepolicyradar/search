from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from statistics import mean

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
            "service.instance.id": "relevance",
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


def score_averages[I, O, M](
    report: EvaluationReport[I, O, M],
) -> dict[str, float]:
    """Average scores by evaluation name, merging the copies pydantic_evals suffixes with _2."""
    scores: dict[str, list[float]] = defaultdict(list)
    for case in report.cases:
        for result in case.scores.values():
            scores[result.name].append(result.value)

    return {name: mean(values) for name, values in scores.items()}


def report[I, O](
    meter: Meter,
    dataset_name: str,
    report: EvaluationReport[I, O, dict[str, str]],
) -> None:
    branch = common.branch()

    score_gauge = meter.create_gauge(
        description="Per-suite average evaluator scores",
        name="relevance_score",
        unit="1",
    )

    for name, value in score_averages(report).items():
        score_gauge.set(
            attributes={"suite": dataset_name, "metric": name, "branch": branch},
            amount=value,
        )

    if (averages := report.averages()) and averages.assertions is not None:
        score_gauge.set(
            attributes={"suite": dataset_name, "metric": "pass_rate", "branch": branch},
            amount=averages.assertions,
        )

    error_counter = meter.create_counter(
        description="Evaluator cases that errored",
        name="relevance_errors",
        unit="1",
    )

    error_counter.add(
        attributes={"suite": dataset_name, "branch": branch},
        amount=len(report.failures),
    )
