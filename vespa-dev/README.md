# vespa-dev

## Prerequisites

- Logged into AWS: `aws sso login --profile production`, then
  `export AWS_PROFILE=production AWS_DEFAULT_REGION=eu-west-1`

## Usage

- `just create <instance>`
- [Go to the `search-vespa-dev-feed-from-production` deployment](https://app.prefect.cloud/account/4b1558a0-3c61-4849-8b18-3e97e0516d78/workspace/1753b4f0-6221-4f6a-9233-b146518b4545/deployments/deployment/e3064f9d-6dde-47fb-9029-0a39ee3afc25)
- "Run" the flow with the `<instance>` value from above
- If you want a sample, update the `sample_percent`
- Wait 🥱…

## Changing the feed flow

```bash
just release        # docker-build + docker-push + prefect_deploy
```

For a quick local run against your working copy (bypasses the image):

```bash
just feed-local <instance>
```

## Usage in `./api`

```bash
cd ../api
just gen-env <instance>
```

Visit `http://127.0.0.1:8000/search/documents`
