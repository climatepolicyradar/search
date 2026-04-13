# trunk-ignore-all(checkov,terrascan,hadolint)
# Build from the vespa-feeder directory:
#   docker build -t vespa-feeder .

FROM python:3.13-slim-bookworm

WORKDIR /app

# Install build essentials, curl (health checks), git (git deps), vespa CLI
RUN apt-get update && apt-get install -y build-essential curl git && rm -rf /var/lib/apt/lists/*

# Install vespa CLI
RUN curl -fsSL https://raw.githubusercontent.com/vespa-engine/vespa/master/client/go/install.sh | sh

# Install uv and sync dependencies
RUN pip install uv
COPY pyproject.toml README.md ./
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Copy source
COPY src/ ./src/

ENTRYPOINT ["uv", "run", "python", "-m", "vespa_feeder.flow"]
