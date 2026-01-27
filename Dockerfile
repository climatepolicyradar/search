# Builder stage with full image, as we need compilation software
FROM python:3.13-bookworm@sha256:aba8a0cd72f259c2737c8a47050652036c8bc8266a4f39291523a45cf8081960 AS builder
COPY --from=ghcr.io/astral-sh/uv@sha256:f64ad69940b634e75d2e4d799eb5238066c5eeda49f76e782d4873c3d014ea33 /uv /uvx /bin/

# Install git for git dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

# Copy project files for installation
COPY pyproject.toml README.md ./
COPY search ./search/
COPY scripts ./scripts/
COPY relevance_tests ./relevance_tests/

# Install all dependencies including editable project (requires git for knowledge-graph dependency)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -e . --link-mode=copy

# Runtime stage with slim image
FROM python:3.13-slim-bookworm@sha256:9b8102b7b3a61db24fe58f335b526173e5aeaaf7d13b2fbfb514e20f84f5e386

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the project into the image
COPY pyproject.toml README.md ./
COPY search ./search/
COPY scripts ./scripts/
COPY relevance_tests ./relevance_tests/

# Set PYTHONPATH to ensure modules can be found
ENV PYTHONPATH="/app:/app/search:/app/scripts"

ENV PREFECT_LOGGING_LEVEL=DEBUG
# Setting PYTHONUNBUFFERED to a non-empty value different from 0 ensures that the python output i.e. the stdout and stderr streams are sent straight to terminal
ENV PYTHONUNBUFFERED=1
# Enable Python fault handler for better debugging
ENV PYTHONFAULTHANDLER=1
