# Errors must surface, never be swallowed

A `200` is an assertion that we answered the question we were asked. Never
return one for a request we could not serve.

The failure mode to avoid is the **semipredicate problem**: signalling failure
with a value that is indistinguishable from a legitimate result. A search that
returns `200 {"results": []}` because Vespa timed out is lying: `[]` is a
perfectly valid answer to "find me documents about X". The client cannot tell an
outage from a genuinely empty result set, renders one as the other, and our
metrics record the outage as a success.

So:

- **Distinguish "no data" from "no answer."**
  - Nothing matched → `200` with an empty list.
  - A dependency failed → `5xx`. These are different questions with different
    answers.
- **Never signal failure in-band.** `None`, `[]`, `{}`, `0`, `""` and `-1` are
  all valid values somewhere in the domain. Raise a typed exception instead —
  that is an out-of-band channel the caller cannot accidentally ignore.
- **Log level should match state.** The severity you log at is a claim about the
  state of the system, and the surrounding code has to back that claim up.
  - `logger.error` should throw. Otherwise we swallow the error with a log trail
    nobody reads.
  - `logger.info` / `logger.warning` should return a valid answer, not throw.
- **Throw low, catch once at the boundary.** Raise where the failure happens;
  translate it for the caller in exactly one place. A handler copy-pasted per
  route or per call site is a rule the next one will forget.
- **Make the invariant type-checkable.** Prefer a non-optional return type so
  that `return None` on an error path is a pyright error rather than a silent
  behaviour change. Do not "fix" such an error by widening the type to `| None`
  unless `None` is genuinely a value in the domain — "this document does not
  exist" — and not a stand-in for "the lookup failed".

## Legitimate exceptions

**The boundary itself.** The layer that translates a failure into a response
logs at ERROR and returns rather than re-raising, because translating the
failure _is_ handling it — that is where the throwing is supposed to stop. Every
layer below the boundary raises; exactly one layer converts. This is the one
place "log an error, don't throw" is correct, and it is correct because the
error still reaches the caller.

**Per-item degradation.** Skipping a single malformed record in a result set of
many, with a `logger.warning`, so one bad row does not take out a whole
response. Bounded and deliberate. It is not licence to swallow a whole-request
failure, and it should never be the reason a response is empty.

## Tensions

One tension worth knowing about: **"log and throw" is widely considered an
anti-pattern** (it produces the same failure logged several times on the way
up). We do it deliberately in `_execute_vespa_query` anyway, because the engine
is the only layer that has the traceback and knows _which_ of the fanned-out
queries died (`documents.search` vs `documents.aggregations`), while the
boundary is the only layer that knows the request. Two logs, two different
facts. If you find yourself adding a third for the same failure, that is the
anti-pattern and you should drop one.

## Further reading

This is a well-named set of problems, which is useful when discussing it in
review.

- **The semipredicate problem** — the defect this page exists to prevent:
  signalling failure with a value indistinguishable from a legitimate result.
  The classic case is C's `atoi("abc")` returning `0`, the same thing it returns
  for `"0"`. Naming it also enumerates the only three fixes: signal out-of-band
  (raise), return a tagged result (`Result`/`Either`/Go's `(value, err)`), or
  use a sentinel genuinely outside the valid domain — which for "a list of
  search results" does not exist, and is why the original code could not be
  patched in place. <https://en.wikipedia.org/wiki/Semipredicate_problem>
- **"Errors should never pass silently. Unless explicitly silenced."** — PEP 20,
  _The Zen of Python_, Tim Peters. The second sentence is the whole of our
  carve-out policy: silencing is allowed, but it has to be a decision someone
  wrote down. <https://peps.python.org/pep-0020/>
- **Fail-fast** — Jim Gray, _Why Do Computers Stop and What Can Be Done About
  It?_ (Tandem Technical Report 85.7, 1985), which introduced fail-fast modules;
  and Jim Shore, _Fail Fast_ (IEEE Software, Sept/Oct 2004) for the short
  practitioner version. A component should report failure at its own boundary
  rather than continue in a state it cannot vouch for. A swallow is the exact
  opposite: it manufactures a plausible answer out of a failure.
- **Make illegal states unrepresentable** — Yaron Minsky, _Effective ML_. The
  justification for the non-optional return type: compilers do not forget rules,
  whereas reviewers and context windows do.
- **Let it crash** — Joe Armstrong, _Making Reliable Distributed Systems in the
  Presence of Software Errors_ (2003). "Throw low, catch once at the boundary"
  is this idea at function granularity: let the failure reach a layer that has
  the context to decide what it means, instead of guessing locally.

## Where this is applied

- `api/CLAUDE.md` — the HTTP boundary: status codes, response bodies, and the
  single `VespaError` handler.
- `search/engines/` — engine methods raise `VespaError`
  (`search/engines/__init__.py`) and never return an empty result set for a
  failed query. See `_execute_vespa_query` in `search/engines/dev_vespa.py`.

Covered by `tests/api/test_vespa_unavailable.py` (every route returns `503`,
no-matches is still a `200`, and an error response is not logged as a success)
and `tests/engines/test_dev_vespa_errors.py` (each failure mode raises, and no
caller swallows it). If you add a route or an engine method that calls a
dependency, add it there.
