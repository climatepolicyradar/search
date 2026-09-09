"""
Grafana Cloud k6 projects, load tests, and schedules for search-api.

Split into its own Pulumi project (separate from `search/infra`) so that
updating a k6 script only ever runs a `pulumi up` scoped to these resources —
not the full search-api stack (AppRunner, ECS, S3, IAM, Vespa config), which
would otherwise risk rolling in whatever else happens to have drifted or been
queued up in that stack at the same time.

Manages two k6 Cloud projects per `k6/tests/smoke-load/routes/<resource>/` group:

- `SMOKE: search-api <resource>` — CI's smoke workflow report here
- `LOAD: search-api <resource>` — Load tests report here, run on a
  schedule or manually in the Grafana web UI instead of GitHub Actions
  so sustained load does not consume GitHub runner minutes.

Kept separate rather than sharing one Grafana project per resource because
Grafana Cloud k6 has no per-test/schedule way to set `PROFILE` at cloud-run 
time (only an org-wide env var setting, too coarse to tell one
script's smoke run from its own load run) — mixing both test types into one
project would mean unrelated run shapes sitting in the same history with no
way to tell which is which. See each script's `resolveProfile` — it prefers
`load` over `smoke` for the same reason: nothing can pass `-e PROFILE=load` to
a cloud-triggered run, so the script's own default has to already be right.

`LOAD_TESTS` is the single place to add a route once its load profile lands
 — everything else here is generic over that list.
"""

from dataclasses import dataclass
from pathlib import Path

import pulumi
from pulumiverse_grafana import Provider, k6

# This file lives at <repo>/k6/infra/__main__.py — the k6 scripts it uploads
# live at <repo>/k6/tests/smoke-load/routes/. Computed relative to this file
# rather than via the `search` package's REPO_ROOT_DIR helper, since this is
# a standalone Pulumi project with no dependency on the main search Python
# package.
K6_DIR = Path(__file__).resolve().parent.parent

# Already exists in Grafana and imported into this stack — see module docstring.
SMOKE_RESOURCES = ["documents", "passages", "labels"]


@dataclass(frozen=True)
class LoadTestSpec:
    """One route's graduated load test."""

    resource: str  # k6/tests/smoke-load/routes/<resource>/ group, also the LOAD project name
    script_path: str  # relative to k6/, e.g. "tests/smoke-load/routes/documents/{document_id}/index.ts"
    name: str  # human-friendly load test name in Grafana Cloud
    cron: str  # 5-field cron expression, evaluated in UTC
    starts: str  # RFC3339 timestamp; fixed rather than computed at apply time, so re-running `pulumi up` doesn't perpetually diff the schedule's start


# One entry per route whose `load` profile has graduated —
# each becomes one scheduled Grafana Cloud k6 load test, and implicitly, one
# `LOAD:` project for its resource (unlike SMOKE_RESOURCES above, a resource
# only gets a LOAD project once it actually has a graduated load test).
#
# `name` matches each script's own `options.cloud.name` (the string passed to
# resolveProfile) so a run started from this schedule groups under the same
# name a manual/CI run of the same script would use.
#
# `cron` is a single weekly slot per script, deliberately staggered so no two
# of these ~25min, 50-VU ramps overlap — each one already exercises search-api
# on its own; running two concurrently would conflate their results with each
# other's load. All times UTC, chosen outside CPR's core working hours.
LOAD_TESTS: list[LoadTestSpec] = [
    LoadTestSpec(
        resource="documents",
        script_path="tests/smoke-load/routes/documents/{document_id}/index.ts",
        name="documents/{document_id}: base query",
        cron="0 3 * * 1",  # Monday 03:00 UTC
        starts="2026-09-14T03:00:00Z",
    ),
    LoadTestSpec(
        resource="documents",
        script_path="tests/smoke-load/routes/documents/fields-combinations.ts",
        name="documents: fields combinations",
        cron="0 4 * * 1",  # Monday 04:00 UTC
        starts="2026-09-14T04:00:00Z",
    ),
    LoadTestSpec(
        resource="passages",
        script_path="tests/smoke-load/routes/passages/index.ts",
        name="passages: base query",
        cron="0 3 * * 2",  # Tuesday 03:00 UTC
        starts="2026-09-15T03:00:00Z",
    ),
    LoadTestSpec(
        resource="passages",
        script_path="tests/smoke-load/routes/passages/filter-combinations.ts",
        name="passages: filter combinations",
        cron="0 4 * * 2",  # Tuesday 04:00 UTC
        starts="2026-09-15T04:00:00Z",
    ),
]


def create_k6_load_test_resources(
    provider: Provider,
) -> dict[str, k6.Project]:
    """Manage the SMOKE projects and create any graduated load tests."""
    smoke_projects = {
        resource: k6.Project(
            f"k6-project-{resource}",
            # Matches each project's existing Grafana name exactly (set by hand
            # when these were created for the CI smoke tests, see k6/README.md).
            name=f"SMOKE: search-api {resource}",
            opts=pulumi.ResourceOptions(provider=provider),
        )
        for resource in SMOKE_RESOURCES
    }

    load_resources = {spec.resource for spec in LOAD_TESTS}
    load_projects = {
        resource: k6.Project(
            f"k6-load-project-{resource}",
            name=f"LOAD: search-api {resource}",
            opts=pulumi.ResourceOptions(provider=provider),
        )
        for resource in load_resources
    }

    for spec in LOAD_TESTS:
        script_content = (K6_DIR / spec.script_path).read_text()

        load_test = k6.LoadTest(
            f"k6-load-test-{spec.resource}-{spec.name}",
            project_id=load_projects[spec.resource].id,
            name=spec.name,
            script=script_content,
            opts=pulumi.ResourceOptions(provider=provider),
        )

        k6.Schedule(
            f"k6-schedule-{spec.resource}-{spec.name}",
            load_test_id=load_test.id,
            starts=spec.starts,
            cron=k6.ScheduleCronArgs(schedule=spec.cron, timezone="UTC"),
            opts=pulumi.ResourceOptions(provider=provider),
        )

    return {**smoke_projects, **load_projects}


config = pulumi.Config()
grafana_provider = Provider(
    "grafana",
    k6_access_token=config.get_secret("k6_cloud_token"),
    stack_id=config.get_int("k6_cloud_stack_id"),
)
create_k6_load_test_resources(grafana_provider)
