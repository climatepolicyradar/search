// __ENV reads a variable passed on the command line, e.g. `-e BASE_URL=...`.
// Defaults to production so `k6 run` works out of the box with no setup.
// https://grafana.com/docs/k6/latest/using-k6/k6-options/environment-variables/
export const BASE_URL =
  __ENV.BASE_URL || "https://api.climatepolicyradar.org/search";

// A VU ("virtual user") is one simulated concurrent user — it runs a script's
// default-exported function in a loop for `duration`. Each script defines its
// own PROFILES map (VUs/duration differ per route, and a `load` profile is
// added per-script once that route's load test is scoped) and passes it here
// to pick one via `-e PROFILE=<name>` (defaulting to `smoke`).
// https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/
//
// `cloudName` sets `options.cloud.name`, the identifier Grafana Cloud k6 uses
// to group a script's runs. Without it, Cloud falls back to the script's own
// filename — multiple routes named `index.ts` (the base-query convention,
// see k6/README.md's Layout section) then collide under one indistinguishable
// "index.ts" name in the project's runs list. Passing a route-qualified name
// here (e.g. "documents/{document_id}: base query") keeps every script's runs
// separately identifiable regardless of its filename.
export function resolveProfile(
  cloudName: string,
  profiles: Record<string, object>,
): object {
  const profile = profiles[__ENV.PROFILE || "smoke"] as
    | Record<string, unknown>
    | undefined;
  if (!profile) return profile as unknown as object;
  return { ...profile, cloud: { name: cloudName } };
}
