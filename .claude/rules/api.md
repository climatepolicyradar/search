---
paths: [api/**]
---

# Search API

This is a Vespa search API. It is located in a monorepo which includes a bunch
of data science experiments, Prefect tasks for data feeding etc.

## Code Conventions

### Existing code

Existing code may not meet the conventions below. When coming across it: flag,
change if small, leave if a large change. Be pragmatic.

### All new IO should be async, no blocking calls

We're just waiting for Vespa so asyncio is a natural fit to avoid occupying
threads for no reason. If reusing blocking code from outside the api/ repo, flag
& convert.

## Dependency injection

Exactly one instance of stateful clients / resources, managed with a context
manager. These must be instantiated within the app lifecycle in `main.py` and
stored in the `state` typed dict. Routes then access them directly with deps, as
in `app/state.py`.

### Type Safety

We consider Python to be a statically typed language. Prefer discriminated
unions and dataclasses to dicts / tuples.
