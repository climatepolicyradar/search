# trunk-ignore-all(checkov,terrascan,hadolint)
FROM prefecthq/prefect:3-python3.13

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

ARG VESPA_CLI_VERSION=8.675.23
RUN curl -fsSL "https://github.com/vespa-engine/vespa/releases/download/v${VESPA_CLI_VERSION}/vespa-cli_${VESPA_CLI_VERSION}_linux_amd64.tar.gz" \
    | tar -xzf - -C /usr/local/bin --strip-components=2 "vespa-cli_${VESPA_CLI_VERSION}_linux_amd64/bin/vespa"

WORKDIR /opt/prefect/vespa-dev
ENV PYTHONPATH=/opt/prefect/vespa-dev

# Install Python deps first so this layer is cached independently of source changes.
COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY feed_from_production.py .
COPY export_production_snapshot.py .
