---
name: prefect-vespa-feed-debug
description:
  Use when a search-vespa-feeder Prefect flow run (documents or passages feed)
  has failed, looks stuck, or you need to find out whether specific documents
  actually made it into production Vespa
---

# Prefect + Vespa feed debug workflow

Auth prerequisite: `source .venv/bin/activate` (repo venv has `prefect` CLI
pre-configured against the prod workspace). If any `aws` call errors with "Token
has expired", run `aws sso login --profile production` first — this opens a
browser, works fine non-interactively once approved.

Always pass `--profile production` on `aws` commands.

## Step 1 — Get the flow run's actual state

```bash
prefect flow-run inspect <flow-run-id>
```

Read `state.type` and `state.message` first. Two shapes:

- **`Failed` with a `VespaFeederFailed` message** → go to Step 2.
- **`Running` for much longer than expected** (passages: ~4.5-5.5h for a clean
  run, documents: well under an hour — smaller corpus) → probably a zombie, go
  to Step 3. Don't trust logs alone here — see why below.

## Step 2 — Failed run: read the run-summary artifact

`VespaFeederFailed` fires whenever `missing > 0` for any batch OR any batch task
raised — these are different failure modes with the same exception type. Check
Prefect task-run states for `feed_batch-*` under the flow run: if they are all
`Completed`, nothing raised — the failure is a record-count mismatch, not a
crash.

Pull the artifact (CLI `prefect artifact inspect` needs a key, not an id — use
the Python client to fetch by id from the flow-run-overview URL's
`selected_id`):

```python
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import ArtifactFilter, ArtifactFilterId

async with get_client() as client:
    artifacts = await client.read_artifacts(
        artifact_filter=ArtifactFilter(id=ArtifactFilterId(any_=["<artifact-id>"]))
    )
    print(artifacts[0].data)  # markdown: per-file OK/missing counts
```

The markdown lists which `*.derived.jsonl` file-groups lost records and how
many. "Sample failed documents" is often blank — it's only populated when the
`vespa feed` CLI's own stderr emitted a `giving up` line
(`vespa-feeder/vespa_feeder.py` `_GIVING_UP_RE`); a blank sample does not mean
no data was lost, just that this one extraction path didn't fire.

## Preventive guardrails (already in place)

Both flows now have `timeout_seconds` set (`passages_flow.py`,
`documents_flow.py` — 8h / 3h) so a wedge fails at a known bound instead of
running for days, and fires the existing `on_failure`/`on_crashed` Slack hooks
(`slack_notify.py`, channel `prod-updates`) since a timeout is a real terminal
state, unlike a true wedge.

There's also a Prefect Automation (`vespa-feeder/automations.py`, name
`vespa-feeder-stale-heartbeat-cancel`) that cancels a flow run after 15 minutes
without a `prefect.flow-run.heartbeat` event — much faster than the timeout,
since it reacts to the actual wedge signature rather than overall runtime.
Cancelling lets the ECS worker's own cancellation handling stop the Fargate
task, same effect as the manual Step 3 below but automatic. It's applied by
`just deploy` (`vespa-feeder/justfile`) alongside the flow deployments, so a
merge to `main` that changes the threshold picks it up automatically — no
separate manual step needed.

If a run still ends up stuck despite both of these (e.g. the automation is
disabled, or the whole process is too wedged to respond to cancellation), fall
back to the manual check below.

## Step 3 — Running forever: confirm zombie vs genuinely slow

The known mechanism: a `feed_batch` task that _raises_ (as opposed to returning
its errors in the result) wedges the flow in `Running` forever — heartbeats and
the log worker die silently, no `Failed` state, no artifact. Confirm it's really
wedged, don't assume:

```bash
# Task runs stuck in Running with end_time=None, frozen since batch-count's worth
# of task starts ago (8 for passages, 4 for other feeders) confirms the pattern.
prefect flow-run inspect <flow-run-id>   # get infrastructure_pid

aws ecs describe-tasks --cluster <cluster-name-from-infra_pid> \
  --tasks <task-id-from-infra_pid> --profile production --region eu-west-1
```

If the ECS task's `lastStatus`/`desiredStatus` are still `RUNNING` long past the
expected runtime, it's confirmed wedged — the container is alive but doing
nothing useful. **Fix (confirm with a human first — this affects shared
infra):** cancel the Prefect flow run, then stop the ECS task directly (cancel
alone won't kill Fargate). Check whether queued-but-not-started flow runs are
backed up behind it (a work-pool/queue concurrency limit will block them until
the zombie is cleared).

## Step 4 — Did we actually lose data, or was it transient?

Both document and passage feeds are **idempotent daily full re-feeds**
(`put`/`update` with `create: true`), so by the time you check hours or days
later, a subsequent successful run will have silently overwritten any gap.
Current presence in Vespa only proves "no lasting damage" — it can't tell you
whether the original run truly dropped the write or just miscounted it.

To check current state for specific records:

1. Get the doc IDs straight from the source `.jsonl` (no reconstruction needed —
   each line already has the `put`/`update` key verbatim):
   ```python
   import orjson
   ids = [orjson.loads(line).get("update") or orjson.loads(line).get("put")
          for line in open(path)]
   ```
2. Source files live in S3, never kept post-feed (feeder deletes its local
   derived copies) — bucket/prefix come from `documents_flow.py` /
   `passages_flow.py`:
   `cpr-prod-snowflake-data-export/production/published/ pipeline_data_in_vespa_{documents,passage}_updates_v1/<dated-export>/`.
   Use the dated export folder whose timestamp is just before the flow run's
   `start_time` (`get_latest_s3_export_prefix` picks the same one the feeder
   used).
3. Get the Vespa endpoint/read token (same SSM params the repo's own scripts
   use, see `vespa/justfile` and `vespa-dev/export_production_snapshot.py`):
   ```bash
   aws ssm get-parameter --name "/search/vespa/endpoint" --query Parameter.Value \
     --output text --with-decryption --profile production
   aws ssm get-parameter --name "/search/vespa/read_token" --query Parameter.Value \
     --output text --with-decryption --profile production
   ```
4. Check existence concurrently via the document API — passage IDs may be either
   `{docId}::{idx}` or a bare uuidv7 (prod has held both schemes at different
   times), so just take whatever's after `id:passages:passages::` literally and
   GET:
   ```text
   {endpoint}/document/v1/passages/passages/docid/{id_after_doctype}
   ```
   Keep concurrency modest (~15-40) — a high-concurrency async loop against your
   own laptop's DNS resolver will throw spurious `nodename nor servname` errors
   that look like 404s but aren't; retry those a few times before trusting a
   "missing" verdict.

**Track record so far: every "missing" record checked has turned out to be
present.** This recurs often (roughly half of daily passages runs in the week of
2026-10-14 to 2026-10-20 hit it: always `batches that raised: 0`, always 1-4
records short out of ~10-11M, always blank "sample failed documents"). Ran the
full diff above on two separate incidents (2026-10-18 and 2026-10-20, ~71k IDs
total across 4 flagged batches) — 0 were actually missing from Vespa both times.

**Likely root cause (confirmed, not just a guess):** a known upstream
`vespa feed` bug —
[vespa-engine/vespa#37880](https://github.com/vespa-engine/vespa/issues/37880).
A compressed request can race a pooled buffer that gets reused for the next
document, so a write that actually succeeds server-side can still get reported
as missing client-side. Fixed in
[PR #38152](https://github.com/vespa-engine/vespa/pull/38152), merged
2026-10-08, but not yet in a released `vespa-cli` build as of 2026-10-21 (latest
is v8.763.13, which predates the fix) — `VESPA_CLI_VERSION` in
`vespa-feeder/Dockerfile` still pins 8.675.23. Once a release containing the fix
ships, bump that version and remove `_KNOWN_MISSING_RECORDS_BUG_NOTE` in
`vespa_feeder.py` (it's already wired into both the run-summary artifact and the
`VespaFeederFailed`/Slack message, so no further diagnosis should be needed
until then — but re-verify a few "missing" counts for real after the bump before
trusting it's fully resolved).

## Key files

- `vespa-feeder/vespa_feeder.py` — batch feed, count reconciliation
  (`not_ok_count`), artifact generation, `VespaFeederFailed` raise condition.
- `vespa-feeder/documents_flow.py` / `passages_flow.py` — S3 bucket/prefix per
  feed type.
- `vespa/justfile` — canonical `vespa document get`/`visit` recipes and how
  endpoint/token are fetched.
