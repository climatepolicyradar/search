# search

This file is loaded into every session, so it holds only what applies
everywhere. Run `/init` to have the build, test and architecture detail filled
in.

## Errors must surface, never be swallowed

Never turn a failure into a plausible-looking successful answer. `None`, `[]`,
`0` and `200` are all legitimate results somewhere in the domain, so none of
them can double as a failure signal — the caller has no way to tell which one it
got.

- Raise a typed exception. Do not return a default and log about it.
- The level you log at is a claim about the state of the system: if you
  `logger.error`, throw.
- Translate a failure for the caller in exactly one place, at the boundary.
- Prefer a non-optional return type, so that `return None` on an error path is a
  type error rather than a silent behaviour change.

**Read [docs/errors.md](docs/errors.md) before changing any error path**, and
before adding a route, an engine method, or anything else that calls a
dependency. It covers the reasoning, the two legitimate carve-outs, and the
tests that pin this down.

Layer-specific detail lives next to the code:

- [api/CLAUDE.md](api/CLAUDE.md) — the HTTP boundary: status codes, what goes in
  a response body, and the single `VespaError` handler.
- `search/engines/` — engines raise `VespaError`; they never answer a failed
  query with an empty result set.
