# trunk-ignore-all(checkov,terrascan,hadolint)
FROM prefecthq/prefect:3-python3.13

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

ARG VESPA_CLI_VERSION=8.675.23
RUN curl -fsSL "https://github.com/vespa-engine/vespa/releases/download/v${VESPA_CLI_VERSION}/vespa-cli_${VESPA_CLI_VERSION}_linux_amd64.tar.gz" \
    | tar -xzf - -C /usr/local/bin --strip-components=2 "vespa-cli_${VESPA_CLI_VERSION}_linux_amd64/bin/vespa"

RUN pip install boto3 orjson prefect-slack slack-notify

WORKDIR /opt/prefect/vespa-feeder
COPY flow.py .
