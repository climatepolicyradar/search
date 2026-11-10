# trunk-ignore-all(checkov,terrascan,hadolint)
# @related: PREFECT_VERSION
FROM prefecthq/prefect:3.8.6-python3.13

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

ARG VESPA_CLI_VERSION=8.675.23
RUN curl -fsSL "https://github.com/vespa-engine/vespa/releases/download/v${VESPA_CLI_VERSION}/vespa-cli_${VESPA_CLI_VERSION}_linux_amd64.tar.gz" \
    | tar -xzf - -C /usr/local/bin --strip-components=2 "vespa-cli_${VESPA_CLI_VERSION}_linux_amd64/bin/vespa"

WORKDIR /opt/prefect/vespa-feeder
# `src` so the flow modules keep importing as `vespa_feeder`, `errors` and so
# on - Prefect stores a deployment's entrypoint as a module name, not a path,
# so those names have to resolve exactly as they did before the move.
ENV PYTHONPATH=/opt/prefect/vespa-feeder/src

# Install Python deps first so this layer is cached independently of source changes.
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# The whole source tree, rather than a line per module. Listing files
# individually meant a new module built a working image that crashed on import
# at run time - `errors.py` was added and missed, and nothing caught it until
# the feeder ran. A directory copy cannot drift from what the code imports.
COPY src/ ./src/
