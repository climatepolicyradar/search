# Run reporting: what survives a crash

The feeder reports a run through four channels. They do not fail together, and
the difference matters most in exactly the case you care about: a run that died
without finishing.

Read this before concluding anything from a missing artifact.

## What survives what

| Channel                                                     | Clean finish | Cancel / timeout (SIGTERM) | Crash (SIGKILL, OOM) |
| ----------------------------------------------------------- | ------------ | -------------------------- | -------------------- |
| Markdown run summary artifact                               | yes          | yes                        | **no**               |
| Slack "Records fed" counts                                  | yes          | yes                        | **no**               |
| `runs.completed` / `runs.failed`                            | yes          | neither, by design         | **no**               |
| `run.duration` / `last_run.duration`                        | yes          | yes                        | **no**               |
| `records.fed` / `records.ok` / `records.error`              | yes          | yes                        | **yes**              |
| `records.feeder_errors` / `throttled` / `other_http_errors` | yes          | yes                        | **yes**              |
| `run.batches_expected` / `run.batches_completed`            | yes          | yes                        | **yes**              |
| `run.files_fed`                                             | yes          | yes                        | **yes**              |
| `runs.crashed`                                              | n/a          | n/a                        | **yes**              |

## Why

Everything in the first four rows is written in the drain's `finally` in
`vespa_feeder()`, which runs **inside the flow process**. SIGTERM is catchable,
so a cancel or a flow-level timeout still runs it. SIGKILL is not, so on an OOM
the process dies mid-drain and none of it happens.

The metrics rows survive for a different reason: they are not written at the end
of the run at all. `METRICS_EXPORT_INTERVAL_MS=5000` in `telemetry.py` means
OTel exports whatever has accumulated roughly every 5 seconds, so a crashed run
has already published everything up to its last ~5s.

`runs.crashed` is the exception that proves the rule. It is emitted from
`SlackNotify.on_crashed`, which Prefect runs in a **separate process** that is
still alive after the flow's has died. It flushes explicitly, because that
process exits as soon as the hook returns -- too soon for the periodic export.

## Reading a crashed run

A crash gives you a Prefect "Crashed" state, a Slack message saying progress is
unknown, and these metrics. There is no artifact. That is expected, not a second
fault.

To see how far it got, open the dashboard (the Slack message links to it,
pre-filtered to the deployment) and compare, for that `run_name`:

- `run.batches_completed` against `run.batches_expected` -- the fraction of the
  run that finished
- `records.ok` -- records Vespa actually accepted before the kill

`batches_expected` is set before any feeding starts, so it is present even for a
run that died before its first batch. Without it the completed count has no
denominator and a crash at 80% is indistinguishable from one at 5%.

These are short-lived runs emitting roughly one observation a day, so query them
by grouping on `run_name`. `rate()` and `increase()` are meaningless here.

The dashboard's Runs table shows all of this as one row per run. It is built on
these metrics rather than on logs: it previously parsed a `vespa feed stats:`
line that the v1 removal deleted, and sat empty for six weeks before anyone
noticed. A regex over logs can stop matching silently, and logs die with the
process, so a log-backed table could never report a crashed run at all.

## Partial application in Vespa

A crashed run has usually applied some of its data. `records.ok` is the count
Vespa accepted, and those writes stand -- there is no rollback. The next
scheduled run re-feeds from the current export, so the gap closes on its own
unless the crash is reproducible.

## What this deliberately does not do

The artifact is not written incrementally. Making it crash-proof would mean a
Prefect API call per batch -- roughly 5,900 on a passages run -- to publish a
summary the metrics already carry, and better. The artifact is an end-of-run
document; treat its absence as "the run did not finish", not as "the run did
nothing".
