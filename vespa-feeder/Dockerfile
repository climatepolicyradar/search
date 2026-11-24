# syntax=docker/dockerfile:1
# trunk-ignore-all(checkov)
FROM ghcr.io/astral-sh/uv:0.13.0-python3.13-trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

ARG VESPA_CLI_VERSION=8.788.13
ARG VESPA_CLI_SHA256=a76a15b632fdd35a8cefe281d26581ba29ed049f9b7d5658d2c11c8fe8e4df96

ADD --unpack=true --checksum=sha256:${VESPA_CLI_SHA256} \
    https://github.com/vespa-engine/vespa/releases/download/v${VESPA_CLI_VERSION}/vespa-cli_${VESPA_CLI_VERSION}_linux_amd64.tar.gz /opt/

RUN ln -s /opt/vespa-cli_${VESPA_CLI_VERSION}_linux_amd64/bin/vespa /usr/local/bin/vespa
WORKDIR /opt/prefect/vespa-feeder

# https://docs.astral.sh/uv/guides/integration/docker/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 UV_PYTHON_DOWNLOADS=0 UV_PROJECT_ENVIRONMENT=/usr/local

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=src,target=src \
    uv sync --locked --no-editable

ENTRYPOINT ["tini", "-g", "--"]
