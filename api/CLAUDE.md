# API

The general rule and its reasoning are in [../docs/errors.md](../docs/errors.md)
— read that first. This page is the HTTP-boundary specifics.

## Errors

- **Pick the status code that tells the truth.** `400` the caller's fault, `404`
  genuinely absent, `503` a dependency is unavailable, `500` our bug.
- **Do not leak upstream detail into the response body.** Log the exception,
  return a fixed message — error bodies from a backend can carry queries,
  internals, or tokens.
- **Exception handlers belong on the app, not the route.** `main.py` registers
  one handler per exception type, so a route added later cannot forget it. A
  route that catches and re-raises `HTTPException` itself is duplicating a rule
  that already exists.
- **The lifecycle log takes its level from the status code.** `5xx` → ERROR
  (`Error:`), `4xx` → WARNING (`Rejected:`), otherwise INFO (`Success:`). A
  handled `5xx` logged at INFO as "Success" is invisible to log grepping and
  error alerting — the same blind spot as answering a failed query with a `200`.
  `4xx` warns rather than sinking into INFO because a burst of them is usually a
  caller bug worth seeing; it is safe to warn because nothing alerts on log
  level. See `log_request_lifecycle` in `main.py`.

## How it is wired up

`VespaError` (`search/engines/__init__.py`) is raised by `_execute_vespa_query`
on transport failure, a non-2xx status, or an unparsable body.
`api.main.handle_vespa_error` is the single boundary that turns it into a `503`
with a fixed `{"detail": ...}` body, so routes let it propagate rather than
catching it.

The lifecycle log classifies straight off `http.HTTPStatus`, so the log format
does not depend on the metrics module. `SearchMetrics` classifies separately for
its `http.request.outcome` attribute — deliberately independent, but it does
mean that if you move one threshold (`>= 500`, `>= 400`) you should check
whether the other should move with it.

Covered by `tests/api/test_vespa_unavailable.py`.
