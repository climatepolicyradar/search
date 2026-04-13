# Vespa feeder

A Prefect flow that downloads a JSONL feed file from S3 and pushes it to a Vespa index using the `vespa feed` CLI.

Scales to multiple indexes by running multiple flow deployments with different config.

## How it works

```
S3 (JSONL / JSONL.gz)  →  download  →  vespa feed --target <url>
```

The JSONL format is exactly what the upstream materializer flows produce — no transformation needed.

## Local dev

**Prerequisites:** Docker, [uv](https://docs.astral.sh/uv/), [vespa CLI](https://docs.vespa.ai/en/vespa-cli.html), AWS credentials.

```bash
cp .env.example .env        # fill in your values

just install                # uv sync
just up                     # start local Vespa + LocalStack
just deploy-schema          # deploy Vespa app schema (from repo root)
just run                    # run the flow once (reads .env)
```

To test with a local S3 file instead of real AWS, upload to LocalStack first:

```bash
just localstack-create-bucket
just localstack-upload path/to/my.jsonl

# then point .env at LocalStack:
# AWS_ENDPOINT_URL=http://localhost:4566
# AWS_ACCESS_KEY_ID=test
# AWS_SECRET_ACCESS_KEY=test
```

## Tests

```bash
just test
```

Tests use `moto` for S3 and `unittest.mock` to stub the `vespa feed` subprocess call — no real Vespa or AWS needed.

## Configuration

All config is via environment variables (or a `.env` file):

| Variable | Required | Description |
|---|---|---|
| `VESPA_FEEDER_S3_BUCKET` | yes | S3 bucket containing the feed file |
| `VESPA_FEEDER_S3_KEY` | yes | S3 key, e.g. `search/vespa/docs.jsonl.gz` |
| `VESPA_FEEDER_VESPA_URL` | yes | Vespa endpoint |
| `VESPA_FEEDER_VESPA_WRITE_TOKEN` | no | Bearer token (Vespa Cloud only) |
| `VESPA_FEEDER_INDEX_NAME` | no | Human label for logs (default: `default`) |

## Multi-index usage

Call the flow directly from another Prefect flow:

```python
from vespa_feeder.flow import vespa_feed_flow
from vespa_feeder.config import FeedJob

for index in ["documents", "labels", "passages"]:
    vespa_feed_flow(FeedJob(
        s3_bucket="cpr-cache",
        s3_key=f"search/vespa/{index}_feed_materializer.jsonl.gz",
        vespa_url="https://my-app.vespa-cloud.com",
        vespa_write_token="...",
        index_name=index,
    ))
```

## Triggering from an S3 event (bonus)

The cleanest approach is a **Prefect automation** that listens for a webhook and triggers this deployment.

1. Create a Prefect webhook in the UI (Automations → Webhooks).
2. Configure an S3 EventBridge rule to POST to that webhook URL when the feed file is updated.
3. The automation triggers the relevant `vespa-feed-<index>-prod` deployment.

Alternatively, have the upstream materializer flow call `vespa_feed_flow` directly at the end of its run — no webhook needed.

## Production deployment

```bash
export DOCKER_REGISTRY=<your-ecr-url>
just docker-build
docker push $DOCKER_REGISTRY/vespa-feeder:latest
just deploy   # runs deployments.py
```

`deployments.py` creates one Prefect deployment per index (see `INDEXES` list).  Secrets (`vespa_write_token`, `vespa_url`, `s3_bucket`) are resolved from Prefect Variables at runtime so they can be rotated without redeploying.
