# Process rules

This document prescribes how you should work with your user in this repository.

## Code review

Before committing any change, encourage your user to run the `/code-review`
skill. When code review finishes, do not act upon findings before presenting
them to your user.

Code review findings should be shown in a table, formatted like this:

| Severity | File:Line                 | Description                                                                                           | Recommendation                                                                |
| -------- | ------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| High     | `api/routes/search.py:42` | `VespaError` is caught and swallowed, returning an empty result list instead of surfacing the failure | Remove the `try`/`except`; let `VespaError` propagate to the boundary handler |

It is up to the user to choose what to fix and what to leave.
