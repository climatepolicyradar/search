"""The bounded task runner every feeder flow passes to `@flow`."""

from typing import Any, cast

from prefect.futures import PrefectFuture
from prefect.task_runners import TaskRunner, ThreadPoolTaskRunner


def task_runner(max_workers: int) -> TaskRunner[PrefectFuture[Any]]:
    """
    Build the bounded task runner every feeder flow must pass to `@flow`.

    See the submit loop in `vespa_feeder` for what `max_workers` bounds and
    why the cap has to live on the task runner.

    The cast is unavoidable, not a papered-over mistake: `TaskRunner` is
    `Generic[F]` and invariant, `ThreadPoolTaskRunner` subclasses
    `TaskRunner[PrefectConcurrentFuture[R]]`, and `@flow` declares
    `task_runner: TaskRunner[PrefectFuture[Any]] | None` - so under invariance
    no spelling of Prefect's own default task runner satisfies Prefect's own
    parameter, and pyright rejects all of them. Prefect hits this too and casts
    identically (see `Flow.__init__` in prefect/flows.py). Doing it once here
    keeps the three call sites clean instead of needing two `pyright: ignore`s
    each.
    """
    return cast(
        TaskRunner[PrefectFuture[Any]], ThreadPoolTaskRunner(max_workers=max_workers)
    )
