import os

import pytest
from prefect.testing.utilities import prefect_test_harness


def pytest_configure() -> None:
    # Before any test module imports telemetry, which otherwise builds real
    # OTLP exporters and retries against localhost:4318 for the whole session.
    os.environ.setdefault("DISABLE_OTEL_LOGGING", "true")


@pytest.fixture(scope="session")
def prefect_db():
    """A throwaway Prefect database, for tests that actually run a flow."""
    with prefect_test_harness():
        yield
