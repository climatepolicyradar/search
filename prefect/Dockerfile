# trunk-ignore-all(checkov,terrascan,hadolint)
# 👆all are optimisations which is not the phase of work we are in at the moment

# This file needs to be built from the root of the repo
FROM python:3.13-slim-bookworm

WORKDIR /app

# Install build essentials, curl for health checks, and git for git dependencies
RUN apt-get update && apt-get install -y build-essential curl git && rm -rf /var/lib/apt/lists/*

# Install uv and dependencies
RUN pip install uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked

# needed to run prefect from the path
ENV PATH="/app/.venv/bin:$PATH"

# Copy the application code
COPY ./ /app

# Create data directory (will be populated from S3 at runtime)
RUN mkdir -p /app/data
