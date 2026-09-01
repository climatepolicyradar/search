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
export function resolveProfile<TProfiles extends Record<string, object>>(
  profiles: TProfiles,
): TProfiles[keyof TProfiles] {
  const profileName = (__ENV.PROFILE || "smoke") as keyof TProfiles;
  return profiles[profileName];
}
