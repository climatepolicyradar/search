# Run reporting: what survives a failed or crashed run

Each feeder streams its S3 export into a single `vespa feed` process. That
process prints a stats snapshot every 60 seconds and a final summary when it
exits. `MetricsSink` records each one as it arrives, so a run that dies keeps
what it had reported up to its last snapshot.

## What survives what

| Channel                                                     | Clean finish | Failure (exception) | Cancel / timeout | Crash (SIGKILL, OOM) |
| ----------------------------------------------------------- | ------------ | ------------------- | ---------------- | -------------------- |
| `records.fed` / `records.ok`                                | yes          | to last snapshot    | to last snapshot | to last snapshot     |
| `records.feeder_errors` / `throttled` / `other_http_errors` | yes          | to last snapshot    | to last snapshot | to last snapshot     |
| `records.error`                                             | yes          | from last snapshot  | **no**           | **no**               |
| `run.duration` / `last_run.duration`                        | yes          | from last snapshot  | **no**           | **no**               |
| `runs.completed` / `runs.failed`                            | yes          | `runs.failed`       | neither          | **no**               |
| Slack "Records fed" counts                                  | yes          | from last snapshot  | not verified     | **no**               |
| `runs.crashed`                                              | n/a          | n/a                 | n/a              | **yes**              |

## Why

`records.fed`, `records.ok` and the retry counters are Vespa's own running
counts. `MetricsSink` adds the change since the previous snapshot each minute,
and metrics are exported every 5 seconds, so they survive anything.

`records.error` is the number of operations Vespa did not report as ok. Mid-run
that includes documents still waiting on a retry, so it is only recorded once:
from the final summary on a clean finish, or from the last snapshot when the
stream raises. The duration is recorded at the same point, from Vespa's own feed
time. A cancel or timeout is not an `Exception`, so it records neither.

When the source or a transform fails, `vespa feed` is not killed. It is left to
finish what it was sent and print its summary first, so a failed run usually
reports its true final counts. A cancel, a timeout, or a failure in a later
stage kills it straight away.

`runs.crashed` is emitted from `SlackNotify.on_crashed`, which Prefect runs in a
**separate process** that is still alive after the flow's has died. It flushes
explicitly, because that process exits as soon as the hook returns. That process
cannot see the counts, so a crash message says progress is unknown.

## Reading a crashed run

A crash gives you a Prefect "Crashed" state, a Slack message saying progress is
unknown, and `runs.crashed`. How far it got is in `records.fed` and
`records.ok`, to within a minute.

## Partial application in Vespa

A crashed run has usually applied some of its data. Those writes stand -- there
is no rollback. The next scheduled run re-feeds from the current export, so the
gap closes on its own unless the crash is reproducible.

## A failed run

Records Vespa did not accept raise `RecordsLost` once the feed has finished. A
`vespa feed` that exits non-zero raises `CalledProcessError`, and one whose
summary cannot be read raises a validation error. Either way the run fails with
the traceback in its logs and `runs.failed` is recorded.

A record whose transform raises is logged as a warning with its traceback and
skipped. The feed carries on, and once every other record has been sent the run
fails with `TransformFailures`. After more than 500 such records the feeder
stops sending straight away.
