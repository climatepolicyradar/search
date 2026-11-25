import logging

import typer

from vespa_feeder.passages.flow import feed_passages
from vespa_feeder.stream.metrics import MetricsSink
from vespa_feeder.stream.vespa import VespaFeed


def main(
    target: str = "http://localhost:8080",
    application: str = "default.default.default",
) -> None:
    """Feed the latest production passages export into a local Vespa."""
    logging.basicConfig(level=logging.INFO, force=True)
    feed = VespaFeed(target=target, application=application)
    metrics = MetricsSink(deployment_name="local", run_name="cli")
    feed_passages(feed=feed, metrics=metrics)


if __name__ == "__main__":
    typer.run(main)
