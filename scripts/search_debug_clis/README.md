# Search debug CLIs

A set of minimal, scrappy CLIs for running and debugging searches.

## Why?

It speeds up the search debugging lifecycle to be able to get all the
information you need about a search in one place, and boosts _everyone's_ if we
share this code.

Alternatives include things like
`| jq '[.results, .debug_info] | transpose[] | (.[0] | del(.labels, .documents)) + {relevance: .[1].relevance, summaryfeatures: .[1].summaryfeatures}`
🫣

## Contributing

Feel free to (vibe-)code these in any direction that your debugging requires,
and PR the changes so others can share in the devx improvement.

**These are assumed to break**, and should not be treated as production code.
Breaking changes should be simple to resolve, as long as the code in these CLIs
stays simple.
